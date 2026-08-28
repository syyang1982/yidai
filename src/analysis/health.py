"""Financial health analysis module.

Checks:
  1. debt_ratio < 0.70
  2. current_ratio > 1.0 (skip if data missing)
  3. interest_bearing_debt_ratio < 0.30 (skip if data missing)
  4. debt_to_equity < 2.0 (skip if data missing)

Warnings:
  - debt_ratio > 60%: ⚠ 高负债率警告 (does not affect scoring, only flagged)

Scoring: all pass=5, 1 fail=4, 2 fail=3, 3+ fail=1
Note: skipped checks don't count toward denominator.
"""


def score(data: dict, previous_data: dict | None = None) -> dict:
    """Score financial health based on debt and liquidity metrics.

    Args:
        data: dict with keys 'debt_ratio', 'current_ratio',
              'interest_bearing_debt_ratio', 'debt_to_equity'
        previous_data: optional prior-period health data dict.  When
            provided with a 'debt_ratio' key the function checks whether
            debt_ratio is improving or deteriorating over time.

    Returns:
        dict with 'score' (int 0-5) and 'details' (list of str)
    """
    details = []
    checks_passed = 0
    total_checks = 0

    # Check 1: debt_ratio < 0.70
    debt_ratio = data.get("debt_ratio")
    if debt_ratio is not None:
        total_checks += 1
        if debt_ratio < 0.70:
            details.append(f"debt_ratio: {debt_ratio:.2%} < 70% - PASS")
            checks_passed += 1
        else:
            details.append(f"debt_ratio: {debt_ratio:.2%} >= 70% - FAIL")
        # High debt ratio warning (> 60%)
        if debt_ratio > 0.60:
            details.append(f"⚠ 高负债率警告: {debt_ratio:.2%} > 60% — 需要关注偿债能力")
    else:
        details.append("debt_ratio: missing - SKIP")

    # Check 2: current_ratio > 1.0
    current_ratio = data.get("current_ratio")
    if current_ratio is not None:
        total_checks += 1
        if current_ratio > 1.0:
            details.append(f"current_ratio: {current_ratio:.2f} > 1.0 - PASS")
            checks_passed += 1
        else:
            details.append(f"current_ratio: {current_ratio:.2f} <= 1.0 - FAIL")
    else:
        details.append("current_ratio: missing - SKIP")

    # Check 3: interest_bearing_debt_ratio < 0.30
    ibd_ratio = data.get("interest_bearing_debt_ratio")
    if ibd_ratio is not None:
        total_checks += 1
        if ibd_ratio < 0.30:
            details.append(f"interest_bearing_debt_ratio: {ibd_ratio:.2%} < 30% - PASS")
            checks_passed += 1
        else:
            details.append(f"interest_bearing_debt_ratio: {ibd_ratio:.2%} >= 30% - FAIL")
    else:
        details.append("interest_bearing_debt_ratio: missing - SKIP")

    # Check 4: debt_to_equity < 2.0
    dte = data.get("debt_to_equity")
    if dte is not None:
        total_checks += 1
        if dte < 2.0:
            details.append(f"debt_to_equity: {dte:.2f} < 2.0 - PASS")
            checks_passed += 1
        else:
            details.append(f"debt_to_equity: {dte:.2f} >= 2.0 - FAIL")
    else:
        details.append("debt_to_equity: missing - SKIP")

    # Avoid division by zero
    if total_checks == 0:
        return {"score": 3, "details": details + ["No data available - neutral score"]}

    failures = total_checks - checks_passed
    score_map = {0: 5, 1: 4, 2: 3, 3: 1, 4: 0}
    final_score = score_map.get(failures, 0)

    # --- Multi-period trend penalty (W3.2) ---
    if previous_data is not None:
        prev_dr = previous_data.get("debt_ratio")
        if prev_dr is not None and debt_ratio is not None:
            if debt_ratio > prev_dr:
                # Deteriorating: apply -1 penalty
                final_score = max(0, final_score - 1)
                details.append(
                    f"⚠ 趋势恶化: debt_ratio {debt_ratio:.2%} > 上期 {prev_dr:.2%} — 额外 -1"
                )
            else:
                details.append(
                    f"趋势改善/持平: debt_ratio {debt_ratio:.2%} <= 上期 {prev_dr:.2%}"
                )

    return {"score": final_score, "details": details}
