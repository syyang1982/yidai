"""Backtest engine V2 — extends V1 with quarterly data, trend filters, and gradual position sizing.

Improvements over V1:
1. Quarterly financial data support (not just annual)
2. Trend filter (200-day MA + max drawdown stop)
3. Gradual position sizing (BUY=50%, ADD=25%, REDUCE=50%, EXIT=rest)
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.data.models import _compute_grade, _compute_signal
from src.analysis import profitability, health, cashflow, valuation, growth
from src.strategy.backtest import (
    _parse_date,
    _find_next_price,
    _compute_pe_ratio,
    _compute_pe_percentile,
    _compute_metrics,
)


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "use_quarterly": True,
    "trend_filter_enabled": True,
    "ma_period": 200,
    "max_drawdown_stop": 0.30,
    "position_sizing": "gradual",
    "buy_pct": 0.50,
    "add_pct": 0.25,
    "reduce_pct": 0.50,
    "yoy_growth": True,
}


# ---------------------------------------------------------------------------
# Trade cost model
# ---------------------------------------------------------------------------

COMMISSION_RATE = 0.0003   # 0.03% commission
STAMP_TAX_RATE = 0.0013    # 0.13% stamp tax (sell only)
SLIPPAGE_RATE = 0.001      # 0.1% slippage


def _apply_trade_cost(price: float, shares: int, action: str) -> float:
    """Apply commission + stamp tax + slippage to a trade.

    Args:
        price: execution price per share
        shares: number of shares traded
        action: 'BUY' or 'SELL'

    Returns:
        total cost (in currency units) to deduct from cash
    """
    gross = price * shares
    commission = gross * COMMISSION_RATE
    slippage = gross * SLIPPAGE_RATE
    stamp = gross * STAMP_TAX_RATE if action in ("SELL", "REDUCE") else 0
    return commission + slippage + stamp


def _is_annual_period(period: str) -> bool:
    """Check if a period string represents an annual period (FY2024, 2024, etc.)."""
    p = period.upper().strip()
    if p.startswith("FY"):
        return True
    # e.g. "2024" or "2024-12-31" — annual if month is 12 or just year
    try:
        if len(p) == 4:
            int(p)
            return True
    except ValueError:
        pass
    # Check for date-based periods ending in 12-31
    if "-12-31" in period:
        return True
    return False


def _is_quarterly_period(period: str) -> bool:
    """Check if a period represents a quarterly report."""
    return not _is_annual_period(period)


def _get_period_month_day(period: str) -> Optional[Tuple[int, int]]:
    """Extract (month, day) from a period string like '2024-09-30' or 'Q3 2024'."""
    # Date-based: "2024-09-30"
    try:
        if len(period) >= 10 and period[4] == "-":
            parts = period.split("-")
            return (int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        pass
    # "Q3 2024" style
    q_map = {"Q1": (3, 31), "Q2": (6, 30), "Q3": (9, 30), "Q4": (12, 31)}
    for q, md in q_map.items():
        if q in period.upper():
            return md
    return None


def _has_required_fields(fin: dict) -> bool:
    """Check if a financial dict has the minimum fields needed for scoring.

    Quarterly reports often lack capex and FCF, but we can still score them
    on the other dimensions.
    """
    required = ["revenue", "gross_profit", "net_income", "total_assets",
                 "total_liabilities", "total_equity"]
    for field in required:
        if fin.get(field) is None:
            return False
    return True


class BacktestEngineV2:
    """Backtest engine with quarterly data, trend filters, and gradual sizing."""

    def __init__(self, initial_capital: float = 1_000_000, config: Optional[dict] = None,
                 use_cost_model: bool = True):
        self.initial_capital = initial_capital
        self.use_cost_model = use_cost_model
        self.config = {**_DEFAULT_CONFIG}
        if config:
            self.config.update(config)

    # ------------------------------------------------------------------
    # Trend / MA helpers
    # ------------------------------------------------------------------

    def _compute_ma(
        self,
        price_history: List[dict],
        period: int,
        as_of_date: date,
    ) -> Optional[float]:
        """Compute N-day simple moving average from prices up to as_of_date.

        Returns None if fewer than `period` data points are available.
        """
        prices_up_to = [
            p["close_price"]
            for p in price_history
            if _parse_date(p["date"]) <= as_of_date
        ]
        if len(prices_up_to) < period:
            return None
        window = prices_up_to[-period:]
        return sum(window) / len(window)

    def _check_drawdown(
        self,
        peak_value: float,
        current_value: float,
    ) -> bool:
        """Return True if drawdown from peak exceeds max_drawdown_stop."""
        if peak_value <= 0:
            return False
        drawdown = (peak_value - current_value) / peak_value
        return drawdown >= self.config["max_drawdown_stop"]

    # ------------------------------------------------------------------
    # YoY growth helper
    # ------------------------------------------------------------------

    def _get_yoy_growth(
        self,
        financials: List[dict],
        current_idx: int,
    ) -> float:
        """Compute YoY revenue growth for same quarter (or same annual period).

        Looks for a period exactly 1 year before the current one.
        E.g. 2024-09-30 -> 2023-09-30, FY2024 -> FY2023.
        """
        current_period = financials[current_idx]["period"]
        current_rev = financials[current_idx].get("revenue", 0) or 0

        # Find the period exactly 1 year ago
        target_period = self._one_year_ago(current_period)

        for i, fin in enumerate(financials):
            if fin["period"] == target_period:
                prev_rev = fin.get("revenue", 0) or 0
                if prev_rev > 0:
                    return (current_rev - prev_rev) / prev_rev
                return 0.0

        # Fallback: use the immediately previous period (sequential)
        if current_idx > 0:
            prev_rev = financials[current_idx - 1].get("revenue", 0) or 0
            if prev_rev > 0:
                return (current_rev - prev_rev) / prev_rev
        return 0.0

    @staticmethod
    def _one_year_ago(period: str) -> str:
        """Return the period string for exactly 1 year before the given period.

        Handles: '2024-09-30' -> '2023-09-30', 'FY2024' -> 'FY2023', 'Q3 2024' -> 'Q3 2023'
        """
        p = period.strip()

        # Date-based: "2024-09-30"
        if len(p) >= 10 and p[4] == "-":
            try:
                parts = p.split("-")
                year = int(parts[0]) - 1
                return f"{year}-{parts[1]}-{parts[2]}"
            except (ValueError, IndexError):
                pass

        # FYxxxx
        if p.upper().startswith("FY"):
            try:
                year = int(p[2:]) - 1
                return f"FY{year}"
            except ValueError:
                pass

        # Qn yyyy
        upper = p.upper()
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            if upper.startswith(q):
                try:
                    year = int(p[len(q):].strip()) - 1
                    return f"{q} {year}"
                except ValueError:
                    pass

        # Plain year: "2024" -> "2023"
        try:
            year = int(p) - 1
            return str(year)
        except ValueError:
            pass

        return ""

    # ------------------------------------------------------------------
    # Position sizing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _update_entry_price(
        old_shares: int,
        old_entry_price: float,
        new_shares: int,
        new_price: float,
    ) -> float:
        """Compute weighted average entry price after adding shares."""
        total_shares = old_shares + new_shares
        if total_shares <= 0:
            return 0.0
        return (old_shares * old_entry_price + new_shares * new_price) / total_shares

    # ------------------------------------------------------------------
    # Main run method
    # ------------------------------------------------------------------

    def run(
        self,
        ticker: str,
        financials: List[dict],
        price_history: List[dict],
        ownership_scores: Optional[Dict[str, int]] = None,
        strategy_scores: Optional[Dict[str, int]] = None,
        revenue_growth_rates: Optional[Dict[str, List[float]]] = None,
        growth_drivers: Optional[Dict[str, List[str]]] = None,
    ) -> dict:
        """Run backtest for a single stock with V2 enhancements.

        Args:
            ticker: stock ticker
            financials: list of financial dicts (annual AND/OR quarterly), sorted by period ASCENDING
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

        cfg = self.config

        # --- filter financials if not using quarterly ---
        if not cfg["use_quarterly"]:
            filtered = [f for f in financials if _is_annual_period(f["period"])]
            if filtered:
                financials = filtered

        # --- filter out quarterly periods missing required fields ---
        filtered_financials = []
        for fin in financials:
            if _is_quarterly_period(fin["period"]) and not _has_required_fields(fin):
                continue
            filtered_financials.append(fin)
        financials = filtered_financials

        sorted_financials = sorted(financials, key=lambda f: f["period"])
        sorted_prices = sorted(price_history, key=lambda p: _parse_date(p["date"]))

        # --- state ---
        cash = self.initial_capital
        shares = 0
        entry_price = 0.0
        trades: List[dict] = []
        signals_list: List[tuple] = []
        portfolio_values: List[Tuple[str, float]] = []
        benchmark_values: List[Tuple[str, float]] = []
        trend_filter_blocked = 0
        total_trade_cost = 0.0

        # --- benchmark: buy-and-hold from day 1 ---
        benchmark_shares = 0.0
        if sorted_prices and sorted_prices[0]["close_price"] > 0:
            benchmark_shares = self.initial_capital / sorted_prices[0]["close_price"]

        # --- PE history for percentile ---
        pe_history: List[float] = []

        # --- for tracking ADD signals ---
        prev_total_score: Optional[int] = None
        last_reduce_date: Optional[str] = None

        # --- peak portfolio value for drawdown tracking ---
        peak_value = self.initial_capital

        # --- pre-compute consecutive growth rates (for growth dimension) ---
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
                # derive from period string
                try:
                    if _is_annual_period(period):
                        yr = int(period.replace("FY", "").replace("fy", "").strip()[:4])
                        report_date = date(yr + 1, 4, 30)
                    else:
                        # Quarterly — try to parse date from period
                        if len(period) >= 10 and period[4] == "-":
                            report_date = _parse_date(period)
                        else:
                            if sorted_prices:
                                report_date = _parse_date(sorted_prices[-1]["date"])
                            else:
                                continue
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

            # --- revenue growth (YoY if enabled) ---
            if cfg["yoy_growth"]:
                rev_growth_dec = self._get_yoy_growth(sorted_financials, idx)
            else:
                # Sequential (like v1)
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
            # For OCF previous: find the prior period (any type)
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
                # Build growth rates list up to this index
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

            # ==== Trend filter ====
            trend_status = "above_ma"
            if cfg["trend_filter_enabled"] and price_info:
                trade_date, trade_price = price_info
                ma_value = self._compute_ma(
                    sorted_prices, cfg["ma_period"], trade_date
                )
                if ma_value is not None:
                    if trade_price < ma_value:
                        trend_status = "below_ma"

            # ==== Drawdown check ====
            # Check if we should force a REDUCE due to drawdown
            if cfg["trend_filter_enabled"] and price_info:
                trade_date, trade_price = price_info
                current_portfolio_value = cash + shares * trade_price
                if current_portfolio_value > peak_value:
                    peak_value = current_portfolio_value
                if self._check_drawdown(peak_value, current_portfolio_value):
                    if signal not in ("REDUCE",) and shares > 0:
                        signal = "REDUCE"  # force REDUCE on drawdown

            # Append signal (period, signal, scores_dict, total, grade, trend_status)
            signals_list.append((period, signal, scores_dict, total, grade, trend_status))

            # ==== Execute trade ====
            if price_info:
                trade_date, trade_price = price_info

                if cfg["position_sizing"] == "gradual":
                    cash, shares, entry_price, new_trades, blocked = self._execute_gradual(
                        signal=signal,
                        total_score=total,
                        prev_total_score=prev_total_score,
                        cash=cash,
                        shares=shares,
                        entry_price=entry_price,
                        trade_price=trade_price,
                        trade_date=trade_date,
                        trend_status=trend_status,
                        last_reduce_date=last_reduce_date,
                        current_date=str(trade_date),
                    )
                    trades.extend(new_trades)
                    trend_filter_blocked += blocked
                    # Track reduce date for EXIT logic
                    if signal == "REDUCE" and new_trades:
                        last_reduce_date = str(trade_date)
                else:
                    # V1 behavior: full buy / full sell
                    cash, shares, new_trades = self._execute_full(
                        signal=signal,
                        cash=cash,
                        shares=shares,
                        trade_price=trade_price,
                        trade_date=trade_date,
                    )
                    trades.extend(new_trades)

                prev_total_score = total

        # --- daily portfolio & benchmark tracking ---
        trade_events = [("1900-01-01", self.initial_capital, 0)]
        _cash = self.initial_capital
        _shares = 0
        for t in trades:
            if t["action"] == "BUY":
                _shares += t["shares"]
                _cash -= t["value"]
            elif t["action"] == "SELL":
                _cash += t["value"]
                _shares -= t["shares"]
            trade_events.append((t["date"], _cash, _shares))

        ev_idx = 0
        for p in sorted_prices:
            pdate = _parse_date(p["date"])
            pprice = p["close_price"]
            while ev_idx + 1 < len(trade_events) and trade_events[ev_idx + 1][0] <= str(pdate):
                ev_idx += 1
            cur_cash = trade_events[ev_idx][1]
            cur_shares = trade_events[ev_idx][2]
            portfolio_values.append((str(pdate), cur_cash + cur_shares * pprice))
            benchmark_values.append((str(pdate), benchmark_shares * pprice))

        # --- metrics ---
        metrics = _compute_metrics(portfolio_values, benchmark_values, trades)
        metrics["trend_filter_blocked"] = trend_filter_blocked
        total_trade_cost = sum(t.get("trade_cost", 0) for t in trades)
        metrics["total_trade_cost"] = total_trade_cost

        return {
            "trades": trades,
            "portfolio_values": portfolio_values,
            "benchmark_values": benchmark_values,
            "signals": signals_list,
            "metrics": metrics,
        }

    # ------------------------------------------------------------------
    # Gradual execution
    # ------------------------------------------------------------------

    def _execute_gradual(
        self,
        signal: str,
        total_score: int,
        prev_total_score: Optional[int],
        cash: float,
        shares: int,
        entry_price: float,
        trade_price: float,
        trade_date: date,
        trend_status: str,
        last_reduce_date: Optional[str],
        current_date: str,
    ) -> Tuple[float, int, float, List[dict], int]:
        """Execute trade with gradual position sizing.

        Returns: (new_cash, new_shares, new_entry_price, trades, blocked_count)
        """
        cfg = self.config
        trades = []
        blocked = 0
        trade_cost_total = 0.0

        if signal == "BUY":
            if trend_status == "below_ma" and cfg["trend_filter_enabled"]:
                # BUY blocked by trend filter
                blocked = 1
                return cash, shares, entry_price, trades, blocked

            if shares == 0 and cash > 0 and trade_price > 0:
                # Initial BUY — invest buy_pct of cash
                invest_amount = cash * cfg["buy_pct"]
                new_shares = int(invest_amount / trade_price)
                if new_shares > 0:
                    cost = new_shares * trade_price
                    trade_cost = 0.0
                    if self.use_cost_model:
                        trade_cost = _apply_trade_cost(trade_price, new_shares, "BUY")
                        trade_cost_total += trade_cost
                    cash -= (cost + trade_cost)
                    shares = new_shares
                    entry_price = trade_price
                    trades.append({
                        "date": str(trade_date),
                        "action": "BUY",
                        "shares": new_shares,
                        "price": trade_price,
                        "value": cost,
                        "trade_cost": trade_cost,
                        "partial": cfg["buy_pct"] < 1.0,
                    })

            elif shares > 0 and prev_total_score is not None and total_score > prev_total_score:
                # ADD — scores improved while holding
                invest_amount = cash * cfg["add_pct"]
                new_shares = int(invest_amount / trade_price)
                if new_shares > 0 and cash >= new_shares * trade_price:
                    cost = new_shares * trade_price
                    trade_cost = 0.0
                    if self.use_cost_model:
                        trade_cost = _apply_trade_cost(trade_price, new_shares, "BUY")
                        trade_cost_total += trade_cost
                    cash -= (cost + trade_cost)
                    entry_price = self._update_entry_price(
                        shares, entry_price, new_shares, trade_price
                    )
                    shares += new_shares
                    trades.append({
                        "date": str(trade_date),
                        "action": "BUY",
                        "shares": new_shares,
                        "price": trade_price,
                        "value": cost,
                        "trade_cost": trade_cost,
                        "partial": True,
                    })

        elif signal == "REDUCE":
            if shares > 0:
                # Check if this is an EXIT (already reduced recently) or first REDUCE
                is_exit = (last_reduce_date is not None and last_reduce_date == current_date)
                if is_exit:
                    sell_shares = shares
                else:
                    sell_shares = max(1, int(shares * cfg["reduce_pct"]))
                    sell_shares = min(sell_shares, shares)

                if sell_shares > 0:
                    proceeds = sell_shares * trade_price
                    trade_cost = 0.0
                    if self.use_cost_model:
                        trade_cost = _apply_trade_cost(trade_price, sell_shares, "SELL")
                        trade_cost_total += trade_cost
                    remaining = shares - sell_shares
                    cash += (proceeds - trade_cost)
                    shares = remaining
                    trades.append({
                        "date": str(trade_date),
                        "action": "SELL",
                        "shares": sell_shares,
                        "price": trade_price,
                        "value": proceeds,
                        "trade_cost": trade_cost,
                        "partial": sell_shares < (shares + sell_shares),
                    })
                    if shares == 0:
                        entry_price = 0.0

        # HOLD / WATCH → do nothing
        return cash, shares, entry_price, trades, blocked

    # ------------------------------------------------------------------
    # Full execution (v1 behavior)
    # ------------------------------------------------------------------

    def _execute_full(
        self,
        signal: str,
        cash: float,
        shares: int,
        trade_price: float,
        trade_date: date,
    ) -> Tuple[float, int, List[dict]]:
        """Execute trade with full position sizing (v1 behavior).

        Returns: (new_cash, new_shares, trades)
        """
        trades = []

        if signal == "BUY" and shares == 0 and cash > 0 and trade_price > 0:
            new_shares = int(cash / trade_price)
            if new_shares > 0:
                cost = new_shares * trade_price
                trade_cost = 0.0
                if self.use_cost_model:
                    trade_cost = _apply_trade_cost(trade_price, new_shares, "BUY")
                cash -= (cost + trade_cost)
                shares = new_shares
                trades.append({
                    "date": str(trade_date),
                    "action": "BUY",
                    "shares": new_shares,
                    "price": trade_price,
                    "value": cost,
                    "trade_cost": trade_cost,
                    "partial": False,
                })

        elif signal == "REDUCE" and shares > 0:
            proceeds = shares * trade_price
            trade_cost = 0.0
            if self.use_cost_model:
                trade_cost = _apply_trade_cost(trade_price, shares, "SELL")
            trades.append({
                "date": str(trade_date),
                "action": "SELL",
                "shares": shares,
                "price": trade_price,
                "value": proceeds,
                "trade_cost": trade_cost,
                "partial": False,
            })
            cash += (proceeds - trade_cost)
            shares = 0

        return cash, shares, trades

    # ------------------------------------------------------------------
    # Walk-forward validation
    # ------------------------------------------------------------------

    def walk_forward(
        self,
        ticker: str,
        all_financials: List[dict],
        all_prices: List[dict],
        train_years: int = 5,
        test_years: int = 1,
        ownership_scores: Optional[Dict[str, int]] = None,
        strategy_scores: Optional[Dict[str, int]] = None,
        revenue_growth_rates: Optional[Dict[str, List[float]]] = None,
        growth_drivers: Optional[Dict[str, List[str]]] = None,
    ) -> dict:
        """Walk-forward validation.

        Splits financial data into rolling train/test windows, runs the
        backtest on each test window, and aggregates the out-of-sample
        metrics.

        Args:
            ticker: stock ticker
            all_financials: list of all financial dicts (sorted by period ASC)
            all_prices: list of all price dicts (sorted by date ASC)
            train_years: number of years for training (in-sample)
            test_years: number of years for testing (out-of-sample)
            ownership_scores, strategy_scores, revenue_growth_rates,
            growth_drivers: passed through to run()

        Returns:
            dict with:
              - windows: list of per-window results (train_metrics, test_metrics, period)
              - aggregated_test_metrics: average metrics across all test windows
              - n_windows: number of walk-forward windows
        """
        if ownership_scores is None:
            ownership_scores = {}
        if strategy_scores is None:
            strategy_scores = {}
        if growth_drivers is None:
            growth_drivers = {}

        sorted_financials = sorted(all_financials, key=lambda f: f["period"])
        sorted_prices = sorted(all_prices, key=lambda p: _parse_date(p["date"]))

        if not sorted_financials or not sorted_prices:
            return {"windows": [], "aggregated_test_metrics": {}, "n_windows": 0}

        # Extract years from financial periods
        def _period_year(fin: dict) -> int:
            p = fin["period"]
            # Try date-based: 2024-09-30
            if len(p) >= 4 and p[:4].isdigit():
                return int(p[:4])
            # FYxxxx
            if p.upper().startswith("FY") and p[2:].isdigit():
                return int(p[2:])
            # Qn yyyy
            for q in ["Q1", "Q2", "Q3", "Q4"]:
                if p.upper().startswith(q):
                    try:
                        return int(p[len(q):].strip())
                    except ValueError:
                        pass
            return 0

        # Group financials by year
        years = sorted(set(_period_year(f) for f in sorted_financials))
        if len(years) < train_years + test_years:
            # Not enough data — run a single backtest on everything
            result = self.run(
                ticker, sorted_financials, sorted_prices,
                ownership_scores, strategy_scores,
                revenue_growth_rates, growth_drivers,
            )
            return {
                "windows": [{
                    "train_years": years,
                    "test_years": years,
                    "train_metrics": result["metrics"],
                    "test_metrics": result["metrics"],
                }],
                "aggregated_test_metrics": result["metrics"],
                "n_windows": 1,
            }

        windows = []
        step = test_years

        for start_idx in range(0, len(years) - train_years - test_years + 1, step):
            train_year_list = years[start_idx: start_idx + train_years]
            test_year_list = years[start_idx + train_years: start_idx + train_years + test_years]

            if not test_year_list:
                break

            train_min = train_year_list[0]
            train_max = train_year_list[-1]
            test_min = test_year_list[0]
            test_max = test_year_list[-1]

            # Split financials
            train_fin = [f for f in sorted_financials
                         if train_min <= _period_year(f) <= train_max]
            test_fin = [f for f in sorted_financials
                        if test_min <= _period_year(f) <= test_max]

            # Split prices by year
            train_prices = [p for p in sorted_prices
                            if train_min <= _parse_date(p["date"]).year <= train_max + 1]
            test_prices = [p for p in sorted_prices
                           if test_min <= _parse_date(p["date"]).year <= test_max + 1]

            if not test_fin or not test_prices:
                continue

            # Run on train window
            train_result = self.run(
                ticker, train_fin, train_prices,
                ownership_scores, strategy_scores,
                revenue_growth_rates, growth_drivers,
            )

            # Run on test window
            test_result = self.run(
                ticker, test_fin, test_prices,
                ownership_scores, strategy_scores,
                revenue_growth_rates, growth_drivers,
            )

            windows.append({
                "train_period": f"{train_min}-{train_max}",
                "test_period": f"{test_min}-{test_max}",
                "train_metrics": train_result["metrics"],
                "test_metrics": test_result["metrics"],
            })

        # Aggregate test metrics
        metric_keys = [
            "total_return", "cagr", "max_drawdown", "sharpe_ratio",
            "sortino_ratio", "calmar_ratio", "benchmark_return",
            "alpha", "num_trades", "win_rate", "total_trade_cost",
        ]
        aggregated = {}
        if windows:
            for key in metric_keys:
                values = [w["test_metrics"].get(key, 0) for w in windows]
                aggregated[key] = sum(values) / len(values) if values else 0
        else:
            for key in metric_keys:
                aggregated[key] = 0

        return {
            "windows": windows,
            "aggregated_test_metrics": aggregated,
            "n_windows": len(windows),
        }
