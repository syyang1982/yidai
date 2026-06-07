"""Simplified DCF (Discounted Cash Flow) valuation module.

Provides intrinsic value estimation via a simplified DCF model:
  1. Project FCF for N years using provided growth rates
  2. Calculate terminal value via Gordon Growth Model
  3. Discount all cash flows to present value
  4. Derive intrinsic value per share and margin of safety

Scoring (margin of safety based):
  5: margin_of_safety > 30%
  4: margin_of_safety > 15%
  3: margin_of_safety > 0%
  2: margin_of_safety > -15%
  1: else (significantly overvalued)
"""


def simple_dcf(
    current_fcf: float,
    growth_rates: list[float],
    terminal_growth: float,
    discount_rate: float,
    shares_outstanding: float,
) -> dict:
    """Run a simplified DCF model.

    Args:
        current_fcf: most recent free cash flow (absolute, e.g. in CNY/USD)
        growth_rates: list of expected annual FCF growth rates (as decimals,
                      e.g. [0.10, 0.08, 0.06] for 3 years)
        terminal_growth: perpetual growth rate after projection period (decimal)
        discount_rate: WACC / required return (decimal, e.g. 0.10 for 10%)
        shares_outstanding: total shares outstanding

    Returns:
        dict with keys:
            intrinsic_value: intrinsic value per share
            projected_fcfs: list of projected FCFs for each year
            terminal_value: undiscounted terminal value
            pv_fcfs: list of present values of projected FCFs
            pv_terminal: present value of terminal value
    """
    if shares_outstanding <= 0:
        return {
            "intrinsic_value": 0.0,
            "projected_fcfs": [],
            "terminal_value": 0.0,
            "pv_fcfs": [],
            "pv_terminal": 0.0,
        }

    if discount_rate <= terminal_growth:
        # Terminal value formula diverges; use a fallback cap
        terminal_growth = discount_rate - 0.01

    # Project FCFs
    projected_fcfs = []
    fcf = current_fcf
    for rate in growth_rates:
        fcf = fcf * (1 + rate)
        projected_fcfs.append(fcf)

    n_years = len(growth_rates)

    # Terminal value (Gordon Growth Model) based on last projected FCF
    if projected_fcfs:
        last_fcf = projected_fcfs[-1]
        terminal_fcf = last_fcf * (1 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    else:
        # No projection years — terminal value from current FCF
        terminal_fcf = current_fcf * (1 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)

    # Discount projected FCFs to present
    pv_fcfs = []
    for i, f in enumerate(projected_fcfs):
        pv = f / ((1 + discount_rate) ** (i + 1))
        pv_fcfs.append(pv)

    # Discount terminal value to present
    pv_terminal = terminal_value / ((1 + discount_rate) ** n_years) if n_years > 0 else terminal_value

    # Enterprise value = sum of PV of projected FCFs + PV of terminal value
    enterprise_value = sum(pv_fcfs) + pv_terminal

    intrinsic_value = enterprise_value / shares_outstanding

    return {
        "intrinsic_value": intrinsic_value,
        "projected_fcfs": projected_fcfs,
        "terminal_value": terminal_value,
        "pv_fcfs": pv_fcfs,
        "pv_terminal": pv_terminal,
    }


def dcf_valuation(financial_data: dict, price_data: dict) -> dict:
    """Run DCF valuation and return a scoring-friendly result.

    Args:
        financial_data: dict with keys like:
            'fcf' (or 'free_cash_flow'): most recent FCF
            'shares_outstanding': total shares
            'revenue_growth_rates': list of historical growth rates (optional)
            'annual_data': list of yearly financial dicts (optional,
                           each with 'revenue' key for growth estimation)
        price_data: dict with keys like:
            'current_price': current stock price
            'market_cap': market capitalization (optional, for validation)

    Returns:
        dict with 'score' (int 1-5), 'details' (list of str),
        'intrinsic_value' (float), 'margin_of_safety' (float)
    """
    details = []

    # Extract FCF
    fcf = financial_data.get("fcf") or financial_data.get("free_cash_flow")
    if fcf is None:
        details.append("DCF: no FCF data available - score 3 (neutral)")
        return {"score": 3, "details": details, "intrinsic_value": 0.0, "margin_of_safety": 0.0}

    # Negative FCF makes DCF unreliable
    if fcf <= 0:
        details.append(f"DCF: FCF is negative ({fcf:,.0f}) - cannot reliably value, score 1")
        return {"score": 1, "details": details, "intrinsic_value": 0.0, "margin_of_safety": -1.0}

    # Extract shares outstanding
    shares = financial_data.get("shares_outstanding")
    if not shares or shares <= 0:
        details.append("DCF: no shares outstanding data - score 3 (neutral)")
        return {"score": 3, "details": details, "intrinsic_value": 0.0, "margin_of_safety": 0.0}

    # Extract current price
    current_price = price_data.get("current_price")
    if current_price is None or current_price <= 0:
        details.append("DCF: no current price data - score 3 (neutral)")
        return {"score": 3, "details": details, "intrinsic_value": 0.0, "margin_of_safety": 0.0}

    # Estimate growth rates
    growth_rates_input = financial_data.get("revenue_growth_rates")
    if growth_rates_input and len(growth_rates_input) > 0:
        # Use provided growth rates, projected forward (up to 5 years)
        # Take the most recent rates and average them for forward projection
        avg_growth = sum(growth_rates_input) / len(growth_rates_input)
        # Decay growth slightly each year toward terminal
        n_years = min(len(growth_rates_input), 5)
        growth_rates = [avg_growth * (1 - 0.1 * i) for i in range(n_years)]
        details.append(f"DCF: using avg historical growth {avg_growth:.1%}, projected {n_years} years")
    elif financial_data.get("annual_data"):
        avg_growth = estimate_growth_rate(financial_data["annual_data"])
        n_years = 5
        growth_rates = [avg_growth * (1 - 0.1 * i) for i in range(n_years)]
        details.append(f"DCF: estimated growth {avg_growth:.1%} from annual data, projected {n_years} years")
    else:
        # Default conservative growth
        growth_rates = [0.05] * 5
        details.append("DCF: no growth data, using default 5% for 5 years")

    # DCF parameters
    discount_rate = 0.10  # 10% WACC
    terminal_growth = 0.03  # 3% perpetual growth

    details.append(f"DCF: discount_rate={discount_rate:.0%}, terminal_growth={terminal_growth:.0%}")

    result = simple_dcf(
        current_fcf=fcf,
        growth_rates=growth_rates,
        terminal_growth=terminal_growth,
        discount_rate=discount_rate,
        shares_outstanding=shares,
    )

    intrinsic_value = result["intrinsic_value"]
    margin_of_safety = (intrinsic_value - current_price) / intrinsic_value if intrinsic_value > 0 else -1.0

    details.append(f"DCF: FCF={fcf:,.0f}, intrinsic_value={intrinsic_value:.2f}, current_price={current_price:.2f}")
    details.append(f"DCF: margin_of_safety={margin_of_safety:.1%}")

    # Score based on margin of safety
    if margin_of_safety > 0.30:
        score = 5
        details.append(f"DCF score: 5 (margin {margin_of_safety:.1%} > 30%)")
    elif margin_of_safety > 0.15:
        score = 4
        details.append(f"DCF score: 4 (margin {margin_of_safety:.1%} > 15%)")
    elif margin_of_safety > 0:
        score = 3
        details.append(f"DCF score: 3 (margin {margin_of_safety:.1%} > 0%)")
    elif margin_of_safety > -0.15:
        score = 2
        details.append(f"DCF score: 2 (margin {margin_of_safety:.1%} > -15%)")
    else:
        score = 1
        details.append(f"DCF score: 1 (margin {margin_of_safety:.1%} <= -15%)")

    return {
        "score": score,
        "details": details,
        "intrinsic_value": intrinsic_value,
        "margin_of_safety": margin_of_safety,
    }


def estimate_growth_rate(annual_data: list[dict]) -> float:
    """Estimate average revenue growth rate from annual financial data.

    Args:
        annual_data: list of dicts, each with at least a 'revenue' key.
                     Expected to be sorted chronologically (oldest first).

    Returns:
        Average revenue growth rate as a decimal, capped to [-0.20, 0.50].
    """
    if not annual_data or len(annual_data) < 2:
        return 0.05  # default 5% if insufficient data

    revenues = []
    for d in annual_data:
        rev = d.get("revenue") or d.get("total_revenue")
        if rev is not None and rev > 0:
            revenues.append(rev)

    if len(revenues) < 2:
        return 0.05

    growth_rates = []
    for i in range(1, len(revenues)):
        rate = (revenues[i] - revenues[i - 1]) / revenues[i - 1]
        growth_rates.append(rate)

    if not growth_rates:
        return 0.05

    avg_growth = sum(growth_rates) / len(growth_rates)

    # Cap at reasonable bounds
    avg_growth = max(-0.20, min(0.50, avg_growth))

    return avg_growth
