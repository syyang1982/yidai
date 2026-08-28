"""Cash flow analysis module.

Checks:
  1. operating_cash_flow > 0
  2. ocf_to_ni_ratio > 0.7 (OCF should track or exceed net income)
  3. free_cash_flow > 0 (only if data available; None = SKIP)
  4. trend: current OCF vs previous period OCF

Scoring:
  5: all available checks pass + trend ok
  4: all pass but trend declining, or 1 fail
  3: 1 fail + trend declining, or 2 checks with 1 fail
  2: 2 fails
  0: OCF <= 0 (critical - cash-burning company)
"""


def score(data: dict) -> dict:
    """Score cash flow quality.

    Args:
        data: dict with keys 'operating_cash_flow', 'ocf_to_ni_ratio',
              'free_cash_flow' (None if unavailable), 'ocf_current', 'ocf_previous'

    Returns:
        dict with 'score' (int 0-5) and 'details' (list of str)
    """
    details = []
    checks_passed = 0
    total_checks = 0
    trend_ok = True

    # Check 1: operating_cash_flow > 0
    ocf = data.get("operating_cash_flow", 0)
    total_checks += 1
    if ocf > 0:
        details.append(f"operating_cash_flow: {ocf:,.0f} > 0 - PASS")
        checks_passed += 1
    else:
        details.append(f"operating_cash_flow: {ocf:,.0f} <= 0 - FAIL (critical)")

    # Check 2: ocf_to_ni_ratio > 0.7
    ocf_to_ni = data.get("ocf_to_ni_ratio", 0)
    total_checks += 1
    if ocf_to_ni > 0.7:
        details.append(f"ocf_to_ni_ratio: {ocf_to_ni:.2f} > 0.7 - PASS")
        checks_passed += 1
    else:
        details.append(f"ocf_to_ni_ratio: {ocf_to_ni:.2f} <= 0.7 - FAIL")

    # Check 3: free_cash_flow > 0 (only if data available)
    fcf = data.get("free_cash_flow")
    if fcf is not None:
        total_checks += 1
        if fcf > 0:
            details.append(f"free_cash_flow: {fcf:,.0f} > 0 - PASS")
            checks_passed += 1
        else:
            details.append(f"free_cash_flow: {fcf:,.0f} <= 0 - FAIL")
    else:
        details.append("free_cash_flow: data not available - SKIP")

    # Trend check: compare current vs previous period OCF
    ocf_current = data.get("ocf_current")
    ocf_previous = data.get("ocf_previous")
    if ocf_current is not None and ocf_previous is not None and ocf_previous != 0:
        if ocf_current < ocf_previous:
            decline_pct = (ocf_previous - ocf_current) / abs(ocf_previous) * 100
            trend_ok = False
            details.append(
                f"trend: OCF declining ({ocf_current:,.0f} < {ocf_previous:,.0f}, -{decline_pct:.0f}%) - WARNING"
            )
        else:
            details.append(
                f"trend: OCF stable/improving ({ocf_current:,.0f} >= {ocf_previous:,.0f}) - OK"
            )
    else:
        details.append("trend: insufficient data - SKIP")

    # Scoring
    failures = total_checks - checks_passed

    # Critical: OCF <= 0 is an automatic low score
    if ocf <= 0:
        final_score = 0
    elif failures == 0 and trend_ok:
        final_score = 5
    elif failures == 0 and not trend_ok:
        final_score = 4
    elif failures == 1 and trend_ok:
        final_score = 4
    elif failures == 1 and not trend_ok:
        final_score = 3
    elif failures == 2:
        final_score = 2
    else:
        final_score = 1

    return {"score": final_score, "details": details}
