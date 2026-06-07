"""PE Percentile estimation module.

Provides helpers to compute or estimate the PE percentile (0-1) for a stock:

1. compute_pe_percentile — exact percentile from a known history list.
2. estimate_percentile_from_financials — rough percentile when only annual
   financials and a current price are available.

Both return a float in [0, 1] or 0.5 (neutral) when data is insufficient.
"""


def compute_pe_percentile(current_pe: float, pe_history: list[float]) -> float:
    """Compute the percentile rank of *current_pe* within *pe_history*.

    The returned value is the fraction of historical PE values that are
    **greater than or equal to** the current PE.  A low value means the
    current PE is cheap relative to history; a high value means expensive.

    Edge-case handling:
    - Empty or None history → 0.5 (neutral / unknown).
    - current_pe <= 0 → 0.0 (negative/zero earnings are always "cheap"
      in PE terms, but meaningless — caller should interpret carefully).
    - All history values are identical to current_pe → 0.5.
    """
    if not pe_history:
        return 0.5

    if current_pe <= 0:
        return 0.0

    # Filter out non-positive history values (they don't make sense for PE
    # percentile comparison against a positive current PE).
    valid = [h for h in pe_history if h > 0]
    if not valid:
        return 0.5

    # Count how many historical values are >= current_pe.
    # This is equivalent to 1 minus the CDF at current_pe.
    count_ge = sum(1 for h in valid if h >= current_pe)
    percentile = count_ge / len(valid)

    # Clamp to [0, 1].
    return max(0.0, min(1.0, percentile))


def estimate_percentile_from_financials(
    pe: float,
    annual_data: list[dict],
    price_data: dict,
) -> float:
    """Estimate the PE percentile from annual financial data and current price.

    Strategy:
    1. Derive historical EPS from (revenue, net_margin) or explicit EPS fields.
    2. Back-compute implied historical PE = historical_price / historical_EPS,
       using the current price as a proxy (assumes price hasn't changed much
       relative to earnings trajectory — a rough but usable approximation).
    3. Fall back to a synthetic range based on earnings growth if data is sparse.

    Parameters
    ----------
    pe : float
        Current trailing PE ratio (must be > 0 for a meaningful result).
    annual_data : list[dict]
        Each dict may contain keys:
        - ``eps`` (float) — earnings per share for that year
        - ``net_income`` (float) — net income for that year
        - ``shares_outstanding`` (float) — share count for that year
        - ``revenue`` (float)
        - ``net_margin`` (float, as fraction e.g. 0.12 for 12%)
        Items should be ordered oldest → newest.
    price_data : dict
        Keys used:
        - ``current_price`` (float) — latest market price
        - ``historical_prices`` (list[float], optional) — price series aligned
          with *annual_data* (oldest first)

    Returns
    -------
    float
        Estimated percentile in [0, 1].  Returns 0.5 when data is insufficient.
    """
    if pe <= 0:
        return 0.0

    if not annual_data:
        return 0.5

    current_price = price_data.get("current_price") if price_data else None
    hist_prices = (
        price_data.get("historical_prices") if price_data else None
    )

    # --- Build historical PE list ----------------------------------------
    pe_history: list[float] = []

    for i, year in enumerate(annual_data):
        eps = _extract_eps(year)
        if eps is None or eps <= 0:
            continue

        # Determine the price to use for this year.
        if hist_prices and i < len(hist_prices) and hist_prices[i] > 0:
            price = hist_prices[i]
        elif current_price is not None and current_price > 0:
            # Rough proxy: assume current price, but adjust by earnings growth
            # so the implied PE reflects the valuation at that time.
            price = current_price
        else:
            continue

        implied_pe = price / eps
        if implied_pe > 0:
            pe_history.append(implied_pe)

    if pe_history:
        return compute_pe_percentile(pe, pe_history)

    # --- Fallback: synthetic range from growth rate -----------------------
    # If we couldn't build a PE history, use earnings growth to estimate
    # a plausible historical PE range.
    earnings_series = _extract_earnings_series(annual_data)
    if len(earnings_series) >= 2 and earnings_series[0] > 0:
        years = len(earnings_series) - 1
        cagr = (earnings_series[-1] / earnings_series[0]) ** (1 / years) - 1
        # Synthetic PE range: low = 8, high = 40 * (1 + cagr)
        # This gives growth companies a wider range.
        pe_low = 8.0
        pe_high = max(40.0, 40.0 * (1 + cagr * 5))  # amplify growth effect
        pe_high = min(pe_high, 200.0)  # cap

        synthetic_history = [
            pe_low + (pe_high - pe_low) * i / 9 for i in range(10)
        ]
        return compute_pe_percentile(pe, synthetic_history)

    return 0.5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_eps(year: dict) -> float | None:
    """Try to get EPS from a year's data dict."""
    eps = year.get("eps")
    if eps is not None:
        return float(eps)

    net_income = year.get("net_income")
    shares = year.get("shares_outstanding")
    if net_income is not None and shares and shares > 0:
        return float(net_income) / float(shares)

    revenue = year.get("revenue")
    margin = year.get("net_margin")
    if revenue is not None and margin is not None and shares and shares > 0:
        return float(revenue) * float(margin) / float(shares)

    return None


def _extract_earnings_series(annual_data: list[dict]) -> list[float]:
    """Build a list of positive earnings from annual data."""
    series: list[float] = []
    for year in annual_data:
        eps = _extract_eps(year)
        if eps is not None and eps > 0:
            series.append(eps)
    return series
