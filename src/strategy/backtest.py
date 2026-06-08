"""Backtest engine for the 7-dimension scoring strategy.

Simulates what would happen if we followed the scoring signals historically.
No look-ahead bias — signals use only data available at each report date.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from src.data.models import _compute_grade, _compute_signal
from src.analysis import profitability, health, cashflow, valuation, growth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(d: Any) -> date:
    """Parse a date from string or date object."""
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        return datetime.strptime(d, "%Y-%m-%d").date()
    raise ValueError(f"Cannot parse date: {d}")


def _find_next_price(
    price_history: List[dict], target_date: date
) -> Optional[Tuple[date, float]]:
    """Find the first price on or after the given date.

    Args:
        price_history: list of dicts with 'date' and 'close_price', sorted ASC
        target_date: the date to search from

    Returns:
        (date, close_price) or None
    """
    for p in price_history:
        pdate = _parse_date(p["date"])
        if pdate >= target_date:
            return (pdate, p["close_price"])
    return None


def _compute_pe_ratio(price: float, financial: dict) -> Optional[float]:
    """Compute PE ratio from price and financial data.

    Tries EPS first; falls back to shares_outstanding + net_income.
    """
    eps = financial.get("eps")
    if eps is not None and eps > 0:
        return price / eps

    net_income = financial.get("net_income")
    shares = financial.get("shares_outstanding")
    if net_income and net_income > 0 and shares and shares > 0:
        return (price * shares) / net_income

    return None


def _compute_pe_percentile(
    pe_history: List[float], current_pe: float
) -> Optional[float]:
    """Percentile of *current_pe* among all values seen so far (inclusive).

    Returns None when history is empty.
    """
    if not pe_history and current_pe is None:
        return None
    all_pes = [pe for pe in pe_history if pe is not None]
    if current_pe is not None:
        all_pes.append(current_pe)
    if not all_pes:
        return None
    count_le = sum(1 for pe in all_pes if pe <= current_pe)
    return count_le / len(all_pes)


def _compute_metrics(
    portfolio_values: List[Tuple[str, float]],
    benchmark_values: List[Tuple[str, float]],
    trades: List[dict],
) -> dict:
    """Compute backtest performance metrics.

    Returns:
        dict with total_return, cagr, max_drawdown, sharpe_ratio,
        benchmark_return, alpha, num_trades, win_rate
    """
    empty = {
        "total_return": 0,
        "cagr": 0,
        "max_drawdown": 0,
        "sharpe_ratio": 0,
        "benchmark_return": 0,
        "alpha": 0,
        "num_trades": 0,
        "win_rate": 0,
    }
    if not portfolio_values:
        return empty

    initial_value = portfolio_values[0][1]
    final_value = portfolio_values[-1][1]

    # --- total return ---
    total_return = (
        (final_value - initial_value) / initial_value if initial_value else 0
    )

    # --- CAGR ---
    first_date = _parse_date(portfolio_values[0][0])
    last_date = _parse_date(portfolio_values[-1][0])
    years = (last_date - first_date).days / 365.25
    if years > 0 and initial_value > 0 and final_value > 0:
        cagr = (final_value / initial_value) ** (1 / years) - 1
    else:
        cagr = 0

    # --- max drawdown ---
    peak = initial_value
    max_dd = 0.0
    for _, val in portfolio_values:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # --- Sharpe ratio (daily returns, annualised, risk-free = 0) ---
    sharpe = 0.0
    if len(portfolio_values) >= 2:
        daily_rets = []
        for i in range(1, len(portfolio_values)):
            prev = portfolio_values[i - 1][1]
            curr = portfolio_values[i][1]
            if prev > 0:
                daily_rets.append((curr - prev) / prev)
        if daily_rets:
            mean_r = sum(daily_rets) / len(daily_rets)
            var_r = sum((r - mean_r) ** 2 for r in daily_rets) / len(daily_rets)
            std_r = math.sqrt(var_r)
            if std_r > 0:
                sharpe = (mean_r / std_r) * math.sqrt(252)

    # --- benchmark return ---
    benchmark_return = 0.0
    if benchmark_values:
        bm_init = benchmark_values[0][1]
        bm_final = benchmark_values[-1][1]
        if bm_init:
            benchmark_return = (bm_final - bm_init) / bm_init

    # --- alpha ---
    alpha = total_return - benchmark_return

    # --- trade stats ---
    num_trades = len(trades)
    buy_trades = [t for t in trades if t["action"] == "BUY"]
    sell_trades = [t for t in trades if t["action"] == "SELL"]

    win_rate = 0.0
    if buy_trades and sell_trades:
        wins = 0
        complete = 0
        for buy in buy_trades:
            buy_date = _parse_date(buy["date"])
            for sell in sell_trades:
                if _parse_date(sell["date"]) > buy_date:
                    complete += 1
                    if sell["price"] > buy["price"]:
                        wins += 1
                    break
        if complete:
            win_rate = wins / complete

    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "benchmark_return": benchmark_return,
        "alpha": alpha,
        "num_trades": num_trades,
        "win_rate": win_rate,
    }


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """Simulate the 7-dimension scoring strategy historically."""

    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = initial_capital

    # ------------------------------------------------------------------
    def run(
        self,
        ticker: str,
        annual_financials: List[dict],
        price_history: List[dict],
        ownership_scores: Optional[Dict[str, int]] = None,
        strategy_scores: Optional[Dict[str, int]] = None,
        revenue_growth_rates: Optional[Dict[str, List[float]]] = None,
        growth_drivers: Optional[Dict[str, List[str]]] = None,
    ) -> dict:
        """Run backtest for a single stock.

        Args:
            ticker: stock ticker
            annual_financials: list of annual financial dicts, sorted by period ASCENDING
            price_history: list of price dicts sorted by date ASCENDING
            ownership_scores: period -> score (default 4)
            strategy_scores: period -> score (default 4)
            revenue_growth_rates: period -> list of growth rates (overrides auto-compute)
            growth_drivers: period -> list of driver strings

        Returns:
            dict with trades, portfolio_values, benchmark_values, signals, metrics
        """
        if ownership_scores is None:
            ownership_scores = {}
        if strategy_scores is None:
            strategy_scores = {}
        if growth_drivers is None:
            growth_drivers = {}

        sorted_financials = sorted(annual_financials, key=lambda f: f["period"])
        sorted_prices = sorted(price_history, key=lambda p: _parse_date(p["date"]))

        # --- state ---
        cash = self.initial_capital
        shares = 0
        trades: List[dict] = []
        signals: List[tuple] = []
        portfolio_values: List[Tuple[str, float]] = []
        benchmark_values: List[Tuple[str, float]] = []

        # --- benchmark: buy-and-hold from day 1 ---
        benchmark_shares = 0.0
        if sorted_prices and sorted_prices[0]["close_price"] > 0:
            benchmark_shares = self.initial_capital / sorted_prices[0]["close_price"]

        # --- PE history for percentile ---
        pe_history: List[float] = []

        # --- pre-compute consecutive growth rates ---
        growth_rate_list: List[float] = []
        for i in range(1, len(sorted_financials)):
            prev_rev = sorted_financials[i - 1].get("revenue", 0) or 0
            curr_rev = sorted_financials[i].get("revenue", 0) or 0
            growth_rate_list.append(
                (curr_rev - prev_rev) / prev_rev if prev_rev > 0 else 0
            )

        # --- iterate financial periods ---
        for idx, fin in enumerate(sorted_financials):
            period = fin["period"]

            # --- determine report date ---
            report_date_raw = fin.get("report_date")
            if report_date_raw is not None:
                report_date = _parse_date(report_date_raw)
            else:
                # derive: FYxxxx → April 30 of year+1
                try:
                    yr = int(
                        period.replace("FY", "").replace("fy", "").strip()[:4]
                    )
                    report_date = date(yr + 1, 4, 30)
                except (ValueError, IndexError):
                    if sorted_prices:
                        report_date = _parse_date(sorted_prices[0]["date"])
                    else:
                        continue

            # --- price & PE at report date ---
            price_info = _find_next_price(sorted_prices, report_date)
            current_pe: Optional[float] = None
            if price_info:
                current_pe = _compute_pe_ratio(price_info[1], fin)

            # update PE history & percentile
            if current_pe is not None and current_pe > 0:
                pe_percentile = _compute_pe_percentile(pe_history, current_pe)
                pe_history.append(current_pe)
            else:
                pe_percentile = None

            # --- revenue growth (decimal) for this period ---
            if idx > 0:
                prev_rev = sorted_financials[idx - 1].get("revenue", 0) or 0
                curr_rev = fin.get("revenue", 0) or 0
                rev_growth_dec = (curr_rev - prev_rev) / prev_rev if prev_rev > 0 else 0
            else:
                rev_growth_dec = 0.0

            # ==== D1 profitability ====
            revenue = fin.get("revenue", 0) or 0
            denom = revenue if revenue else 1
            prof_input = {
                "revenue_growth": rev_growth_dec,
                "gross_margin": (fin.get("gross_profit", 0) or 0) / denom,
                "net_margin": (fin.get("net_income", 0) or 0) / denom,
                "roe": (
                    (fin.get("net_income", 0) or 0) / (fin.get("total_equity") or 1)
                    if fin.get("total_equity")
                    else 0
                ),
            }
            prof_res = profitability.score(prof_input)

            # ==== D2 health ====
            health_input: Dict[str, Any] = {}
            ta = fin.get("total_assets")
            if ta and ta > 0:
                tl = fin.get("total_liabilities")
                if tl is not None:
                    health_input["debt_ratio"] = tl / ta
                ibd = fin.get("interest_bearing_debt")
                if ibd is not None:
                    health_input["interest_bearing_debt_ratio"] = ibd / ta
            ca = fin.get("current_assets")
            cl = fin.get("current_liabilities")
            if ca is not None and cl and cl > 0:
                health_input["current_ratio"] = ca / cl
            health_res = health.score(health_input)

            # ==== D3 cashflow ====
            ocf = fin.get("operating_cash_flow", 0) or 0
            ni = fin.get("net_income", 0) or 0
            fcf = fin.get("free_cash_flow", 0) or 0
            cf_input: Dict[str, Any] = {
                "operating_cash_flow": ocf,
                "ocf_to_ni_ratio": ocf / ni if ni else 0,
                "free_cash_flow": fcf,
                "ocf_current": ocf,
            }
            if idx > 0:
                cf_input["ocf_previous"] = (
                    sorted_financials[idx - 1].get("operating_cash_flow", 0) or 0
                )
            else:
                cf_input["ocf_previous"] = None
            cf_res = cashflow.score(cf_input)

            # ==== D4 valuation ====
            val_input = {
                "pe_ratio": current_pe,
                "pe_history_percentile": pe_percentile,
                "revenue_growth_rate": rev_growth_dec * 100,  # percentage
            }
            val_res = valuation.score(val_input)

            # ==== D5 growth ====
            if revenue_growth_rates and period in revenue_growth_rates:
                period_gr = revenue_growth_rates[period]
            else:
                period_gr = growth_rate_list[:idx] if idx > 0 else []
            period_drivers = growth_drivers.get(
                period, ["organic growth", "market expansion"]
            )
            grow_res = growth.score({
                "revenue_growth_rates": period_gr,
                "growth_drivers": period_drivers,
            })

            # ==== D6-D7 qualitative ====
            own = ownership_scores.get(period, 4)
            strat = strategy_scores.get(period, 4)

            # ==== total / grade / signal ====
            total = (
                prof_res["score"]
                + health_res["score"]
                + cf_res["score"]
                + val_res["score"]
                + grow_res["score"]
                + own
                + strat
            )
            grade = _compute_grade(total)
            signal = _compute_signal(
                total,
                prof_res["score"],
                health_res["score"],
                cf_res["score"],
                val_res["score"],
                grow_res["score"],
                0,  # dividend_score (not available in backtest)
                own,
                strat,
            )

            scores_dict = {
                "profitability": prof_res["score"],
                "health": health_res["score"],
                "cashflow": cf_res["score"],
                "valuation": val_res["score"],
                "growth": grow_res["score"],
                "ownership": own,
                "strategy": strat,
            }
            signals.append((period, signal, scores_dict, total, grade))

            # ==== execute trade ====
            if price_info:
                trade_date, trade_price = price_info

                if signal == "BUY" and shares == 0 and cash > 0 and trade_price > 0:
                    new_shares = int(cash / trade_price)
                    if new_shares > 0:
                        cost = new_shares * trade_price
                        cash -= cost
                        shares = new_shares
                        trades.append({
                            "date": str(trade_date),
                            "action": "BUY",
                            "shares": new_shares,
                            "price": trade_price,
                            "value": cost,
                        })

                elif signal == "REDUCE" and shares > 0:
                    proceeds = shares * trade_price
                    trades.append({
                        "date": str(trade_date),
                        "action": "SELL",
                        "shares": shares,
                        "price": trade_price,
                        "value": proceeds,
                    })
                    cash += proceeds
                    shares = 0
                # HOLD / WATCH → do nothing

        # --- daily portfolio & benchmark tracking ---
        # Build trade events: list of (trade_date_str, cash_after, shares_after)
        trade_events = [("1900-01-01", self.initial_capital, 0)]
        # Re-simulate trades to get state at each trade date
        _cash = self.initial_capital
        _shares = 0
        for t in trades:
            if t["action"] == "BUY":
                _shares += t["shares"]
                _cash -= t["value"]
            elif t["action"] == "SELL":
                _cash += t["value"]
                _shares = 0
            trade_events.append((t["date"], _cash, _shares))

        def _get_state(trade_date_str: str):
            """Return (cash, shares) active on/after the given trade event."""
            return (trade_events[-1][1], trade_events[-1][2])  # unused, see loop below

        # For each price date, find the most recent trade event
        ev_idx = 0
        for p in sorted_prices:
            pdate = _parse_date(p["date"])
            pprice = p["close_price"]
            # Advance event index if next trade happened on or before this date
            while ev_idx + 1 < len(trade_events) and trade_events[ev_idx + 1][0] <= str(pdate):
                ev_idx += 1
            cur_cash = trade_events[ev_idx][1]
            cur_shares = trade_events[ev_idx][2]
            portfolio_values.append((str(pdate), cur_cash + cur_shares * pprice))
            benchmark_values.append((str(pdate), benchmark_shares * pprice))

        # --- metrics ---
        metrics = _compute_metrics(portfolio_values, benchmark_values, trades)

        return {
            "trades": trades,
            "portfolio_values": portfolio_values,
            "benchmark_values": benchmark_values,
            "signals": signals,
            "metrics": metrics,
        }
