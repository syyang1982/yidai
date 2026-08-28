"""Scorer module -- aggregates 6 quantitative + 2 qualitative dimension scores
into a final ScoreResult.

Dimensions:
  D1 profitability  (quantitative)
  D2 health         (quantitative)
  D3 cashflow       (quantitative)
  D4 valuation      (quantitative)
  D5 growth         (quantitative)
  D6 dividend       (quantitative) -- NEW
  D7 ownership      (qualitative, human-provided 0-5)
  D8 strategy       (qualitative, human-provided 0-5)
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from src.data.models import ScoreResult
from src.analysis import profitability, health, cashflow, valuation, growth, dividend_quality
from src.analysis.benchmarks import get_benchmark
from src.analysis.insider_activity import check_insider_activity


# ---------------------------------------------------------------------------
# Helpers — derive ratio dicts from raw financial data
# ---------------------------------------------------------------------------

def _build_profitability_data(financial_data: dict, prev_financial_data: dict | None,
                              all_annual_data: list | None = None,
                              industry_median_gross_margin: float | None = None) -> dict:
    """Compute revenue_growth, gross_margin, net_margin, roe, and profit quality metrics."""
    revenue = financial_data.get("revenue", 0) or 0
    gross_profit = financial_data.get("gross_profit", 0) or 0
    net_income = financial_data.get("net_income", 0) or 0
    total_equity = financial_data.get("total_equity", 0) or 0

    prev_revenue = 0
    prev_net_income = 0
    if prev_financial_data:
        prev_revenue = prev_financial_data.get("revenue", 0) or 0
        prev_net_income = prev_financial_data.get("net_income", 0) or 0

    revenue_growth = (revenue - prev_revenue) / prev_revenue if prev_revenue else 0
    gross_margin = gross_profit / revenue if revenue else 0
    net_margin = net_income / revenue if revenue else 0
    roe = net_income / total_equity if total_equity else 0

    # Net income growth for profit quality
    net_income_growth = None
    if prev_net_income and prev_net_income > 0:
        net_income_growth = (net_income - prev_net_income) / prev_net_income

    # Multi-year rates for quality trend
    rev_growth_rates = []
    ni_growth_rates = []
    if all_annual_data and len(all_annual_data) >= 2:
        for i in range(1, len(all_annual_data)):
            curr_rev = all_annual_data[i].get("revenue") or 0
            prev_rev = all_annual_data[i - 1].get("revenue") or 0
            if prev_rev > 0:
                rev_growth_rates.append((curr_rev - prev_rev) / prev_rev)
            curr_ni = all_annual_data[i].get("net_income") or 0
            prev_ni = all_annual_data[i - 1].get("net_income") or 0
            if prev_ni and prev_ni > 0:
                ni_growth_rates.append((curr_ni - prev_ni) / prev_ni)

    result = {
        "revenue_growth": revenue_growth,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "roe": roe,
        "net_income_growth": net_income_growth,
        "revenue_growth_rates": rev_growth_rates,
        "net_income_growth_rates": ni_growth_rates,
    }
    # Inject industry median if provided (W3.1)
    if industry_median_gross_margin is not None:
        result["industry_median_gross_margin"] = industry_median_gross_margin
    return result


def _build_health_data(financial_data: dict) -> dict:
    """Compute debt_ratio, current_ratio, interest_bearing_debt_ratio, debt_to_equity."""
    total_assets = financial_data.get("total_assets")
    total_liabilities = financial_data.get("total_liabilities")
    current_assets = financial_data.get("current_assets")
    current_liabilities = financial_data.get("current_liabilities")
    ibd = financial_data.get("interest_bearing_debt")
    total_equity = financial_data.get("total_equity")

    result: Dict[str, Optional[float]] = {}

    if total_assets and total_assets > 0:
        if total_liabilities is not None:
            result["debt_ratio"] = total_liabilities / total_assets
        if ibd is not None:
            result["interest_bearing_debt_ratio"] = ibd / total_assets

    if current_assets is not None and current_liabilities and current_liabilities > 0:
        result["current_ratio"] = current_assets / current_liabilities

    if total_equity and total_equity > 0 and total_liabilities is not None:
        result["debt_to_equity"] = total_liabilities / total_equity

    return result


def _build_cashflow_data(financial_data: dict, prev_financial_data: dict | None) -> dict:
    """Compute ocf_to_ni_ratio and pass through OCF / FCF values.

    FCF is passed as None when data is unavailable (vs 0 when genuinely zero).
    """
    ocf = financial_data.get("operating_cash_flow", 0) or 0
    net_income = financial_data.get("net_income", 0) or 0
    fcf = financial_data.get("free_cash_flow")  # None if not available
    capex = financial_data.get("capex")

    prev_ocf = None
    if prev_financial_data:
        prev_ocf = prev_financial_data.get("operating_cash_flow")

    ocf_to_ni = ocf / net_income if net_income else 0

    return {
        "operating_cash_flow": ocf,
        "ocf_to_ni_ratio": ocf_to_ni,
        "free_cash_flow": fcf,
        "capex": capex,
        "ocf_current": ocf,
        "ocf_previous": prev_ocf,
    }


def _build_valuation_data(financial_data: dict, price_data: dict,
                          prev_financial_data: dict | None = None,
                          peer_median_pe: float | None = None) -> dict:
    """Extract pe_ratio, compute revenue_growth_rate, and derive EV/EBITDA."""
    pe_ratio = price_data.get("pe_ratio") or financial_data.get("pe_ratio")
    pe_hist_pct = price_data.get("pe_history_percentile") or financial_data.get(
        "pe_history_percentile"
    )

    # Compute revenue growth rate from actual financial data
    rev_growth = 0
    curr_rev = financial_data.get("revenue") or 0
    if prev_financial_data:
        prev_rev = prev_financial_data.get("revenue") or 0
        if prev_rev > 0:
            rev_growth = (curr_rev - prev_rev) / prev_rev

    # EV/EBITDA calculation
    ebitda = financial_data.get("ebitda")
    market_cap = price_data.get("market_cap")
    total_debt = financial_data.get("total_liabilities") or 0
    total_equity = financial_data.get("total_equity") or 0
    # Cash approximation: use current_assets if available, else 0
    cash = financial_data.get("current_assets") or 0

    ev = None
    ev_to_ebitda = None
    if market_cap and market_cap > 0:
        # EV = Market Cap + Total Debt - Cash
        # For simplicity: EV ≈ Market Cap + interest_bearing_debt (if available)
        ibd = financial_data.get("interest_bearing_debt")
        if ibd is not None:
            ev = market_cap + ibd - cash
        else:
            # Fallback: use total_equity proxy
            ev = market_cap  # simplified EV
        if ebitda and ebitda > 0:
            ev_to_ebitda = ev / ebitda

    return {
        "pe_ratio": pe_ratio,
        "pe_history_percentile": pe_hist_pct,
        "revenue_growth_rate": rev_growth * 100,  # percentage for PEG calc
        "ebitda": ebitda,
        "ev_to_ebitda": ev_to_ebitda,
        "market_cap": market_cap,
        "peer_median_pe": peer_median_pe,
    }


def _build_growth_data(financial_data: dict,
                       all_annual_data: list | None = None) -> dict:
    """Compute revenue growth rates, 5yr ROE, and 5yr gross margin from multiple annual periods."""
    growth_rates: list[float] = []
    roe_rates: list[float] = []
    gm_rates: list[float] = []

    if all_annual_data and len(all_annual_data) >= 2:
        for i in range(1, len(all_annual_data)):
            curr_rev = (all_annual_data[i].get("revenue") or 0)
            prev_rev = (all_annual_data[i - 1].get("revenue") or 0)
            if prev_rev > 0:
                growth_rates.append((curr_rev - prev_rev) / prev_rev)

        # Collect ROE and gross margin for each year (not just growth periods)
        for d in all_annual_data:
            rev = d.get("revenue") or 0
            gp = d.get("gross_profit") or 0
            ni = d.get("net_income") or 0
            equity = d.get("total_equity") or 0

            if rev > 0:
                gm_rates.append(gp / rev)
            if equity and equity > 0:
                roe_rates.append(ni / equity)

    return {
        "revenue_growth_rates": growth_rates,
        "growth_drivers": [],  # not available from API
        "roe_rates": roe_rates,
        "gross_margin_rates": gm_rates,
    }


def _build_dividend_data(financial_data: dict, price_data: dict,
                         all_annual_data: list | None = None) -> dict:
    """Build dividend quality input data.

    Uses dividend_per_share from financial_data (if available) or
    falls back to computing from total_dividends / shares_outstanding.
    """
    dps = financial_data.get("dividend_per_share") or 0
    shares = financial_data.get("shares_outstanding") or 0
    total_div = financial_data.get("total_dividends") or 0

    # If dps not directly available, try to compute
    if dps == 0 and total_div > 0 and shares > 0:
        dps = total_div / shares

    price = price_data.get("close_price") or 0
    eps = financial_data.get("eps") or 0

    has_dividend = dps > 0
    dy = dps / price if price > 0 else 0
    pr = dps / eps if eps > 0 else None

    # Historical dividend per share for growth trend
    historical_dps = []
    if all_annual_data:
        for d in all_annual_data:
            d_dps = d.get("dividend_per_share") or 0
            d_shares = d.get("shares_outstanding") or 0
            d_total = d.get("total_dividends") or 0
            if d_dps == 0 and d_total > 0 and d_shares > 0:
                d_dps = d_total / d_shares
            historical_dps.append(d_dps)

    return {
        "dividend_yield": dy,
        "payout_ratio": pr,
        "dividend_growth_rates": _compute_dps_growth(historical_dps),
        "has_dividend": has_dividend,
    }


def _compute_dps_growth(dps_list: list[float]) -> list[float]:
    """Compute year-over-year growth rates from a list of DPS values."""
    rates = []
    for i in range(1, len(dps_list)):
        prev = dps_list[i - 1]
        curr = dps_list[i]
        if prev and prev > 0:
            rates.append((curr - prev) / prev)
    return rates


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_all(
    financial_data: dict,
    price_data: dict,
    qualitative_scores: dict,
    prev_financial_data: dict | None = None,
    all_annual_data: list | None = None,
    peer_median_pe: float | None = None,
    industry: str | None = None,
    previous_health_data: dict | None = None,
    insider_activity_events: list[dict] | None = None,
    ownership_structure_events: list[dict] | None = None,
) -> dict:
    """Aggregate all 7 dimension scores and return a result dict.

    Args:
        financial_data: current-period financial statement data (dict).
        price_data: market price / valuation snapshot (dict).
        qualitative_scores: dict with 'ownership_score' and 'strategy_score'
            (each int 0-5).
        prev_financial_data: prior-period financial data for trend calculations.
        all_annual_data: list of annual financial data dicts.
        peer_median_pe: optional peer median PE for valuation comparison.
        industry: optional industry/sector name for benchmark comparisons (W3.1).
        previous_health_data: optional prior-period health data for trend analysis (W3.2).
        insider_activity_events: optional list of insider activity event dicts
            for Check 6 (advisory warning, does NOT affect score).

    Returns:
        dict with keys: ticker, date, profitability_score, health_score,
        cashflow_score, valuation_score, growth_score, ownership_score,
        strategy_score, total_score, grade, signal, details (list of str),
        insider_activity (dict with has_warning, severity, warnings).
    """
    ticker = financial_data.get("ticker", price_data.get("ticker", "UNKNOWN"))
    report_date = financial_data.get("date", price_data.get("date", date.today()))

    # --- D1 profitability ---
    industry_median_gm = None
    if industry:
        bench = get_benchmark(industry)
        industry_median_gm = bench.get("median_gross_margin")
    prof_input = _build_profitability_data(
        financial_data, prev_financial_data, all_annual_data, industry_median_gm
    )
    prof_result = profitability.score(prof_input)

    # --- D2 health ---
    health_input = _build_health_data(financial_data)
    # Build previous health data from prev_financial_data if not explicitly provided
    _prev_health = previous_health_data
    if _prev_health is None and prev_financial_data:
        _prev_health = _build_health_data(prev_financial_data)
    health_result = health.score(health_input, previous_data=_prev_health)

    # --- D3 cashflow ---
    cf_input = _build_cashflow_data(financial_data, prev_financial_data)
    cf_result = cashflow.score(cf_input)

    # --- D4 valuation ---
    val_input = _build_valuation_data(financial_data, price_data, prev_financial_data, peer_median_pe)
    val_result = valuation.score(val_input)

    # --- D5 growth ---
    grow_input = _build_growth_data(financial_data, all_annual_data)
    grow_result = growth.score(grow_input)

    # --- D6 dividend quality (NEW) ---
    div_input = _build_dividend_data(financial_data, price_data, all_annual_data)
    div_result = dividend_quality.score(div_input)

    # --- D7-D8 qualitative (human-provided) ---
    ownership_score = qualitative_scores.get("ownership_score", 0)
    strategy_score = qualitative_scores.get("strategy_score", 0)

    # --- Build ScoreResult (auto-computes total / grade / signal) ---
    sr = ScoreResult(
        ticker=ticker,
        date=report_date,
        profitability_score=prof_result["score"],
        health_score=health_result["score"],
        cashflow_score=cf_result["score"],
        valuation_score=val_result["score"],
        growth_score=grow_result["score"],
        dividend_score=div_result["score"],
        ownership_score=ownership_score,
        strategy_score=strategy_score,
    )

    # Combine detail strings from all modules
    all_details: List[str] = []
    all_details.append("--- Profitability ---")
    all_details.extend(prof_result.get("details", []))
    all_details.append("--- Health ---")
    all_details.extend(health_result.get("details", []))
    all_details.append("--- Cash Flow ---")
    all_details.extend(cf_result.get("details", []))
    all_details.append("--- Valuation ---")
    all_details.extend(val_result.get("details", []))
    all_details.append("--- Growth ---")
    all_details.extend(grow_result.get("details", []))
    all_details.append("--- Dividend Quality ---")
    all_details.extend(div_result.get("details", []))
    all_details.append(f"--- Ownership (qualitative) --- score: {ownership_score}/5")
    all_details.append(f"--- Strategy  (qualitative) --- score: {strategy_score}/5")

    # --- Ownership structure advisory (controller status) ---
    ownership_analysis = None
    if ownership_structure_events:
        from src.analysis.ownership_structure import analyze_controller_status
        ownership_analysis = analyze_controller_status(ownership_structure_events)
        ownership_warnings = ownership_analysis.get("warnings", [])
        if ownership_warnings:
            all_details.append("--- Ownership Structure (advisory) ---")
            all_details.append(f"  分类: {ownership_analysis.get('category', 'unknown')}")
            all_details.append(f"  {ownership_analysis.get('opportunity', '')}")
            for w in ownership_warnings:
                all_details.append(f"  {w}")

    # --- Insider activity advisory (Check 6, does NOT affect score) ---
    insider_result = check_insider_activity(insider_activity_events or [])
    insider_warnings = valuation.check_insider_activity_warning(insider_result)
    all_details.append("--- Insider Activity (advisory) ---")
    all_details.extend(insider_warnings)

    return {
        "ticker": sr.ticker,
        "date": sr.date,
        "profitability_score": sr.profitability_score,
        "health_score": sr.health_score,
        "cashflow_score": sr.cashflow_score,
        "valuation_score": sr.valuation_score,
        "growth_score": sr.growth_score,
        "dividend_score": sr.dividend_score,
        "ownership_score": sr.ownership_score,
        "strategy_score": sr.strategy_score,
        "total_score": sr.total_score,
        "grade": sr.grade,
        "signal": sr.signal,
        "details": all_details,
        "insider_activity": insider_result,
        "ownership_structure": ownership_analysis,
    }


# ---------------------------------------------------------------------------
# Signal text generation
# ---------------------------------------------------------------------------

def generate_signal_text(score_result: dict) -> str:
    """Return a human-readable signal line in Chinese.

    Args:
        score_result: the dict returned by score_all().

    Returns:
        e.g. '🟢 买入 — 优质且便宜' or '🟡 持有'
    """
    signal = score_result.get("signal", "WATCH")
    total = score_result.get("total_score", 0)
    grade = score_result.get("grade", "F")
    valuation = score_result.get("valuation_score", 0)
    health = score_result.get("health_score", 0)

    if signal == "BUY":
        if valuation >= 4 and total >= 33:
            return "🟢 买入 — 优质且便宜"
        return "🟢 买入 — 具备投资价值"

    if signal == "HOLD":
        if total >= 26:
            return "🟡 持有 — 基本面良好"
        return "🟡 持有 — 观察后续表现"

    if signal == "WATCH":
        return "🔵 观望 — 暂不建议介入"

    # signal == "REDUCE"
    if health < 2:
        return "🔴 减仓 — 财务健康堪忧"
    if total <= 8:
        return "🔴 减仓 — 综合评分过低"
    return "🔴 减仓 — 存在明显风险"
