"""Valuation analysis module.

Checks:
  1. PE reasonableness (context-aware for growth companies)
  2. PE_history_percentile < 0.70 (if available)
  3. PEG < 2.0 (for profitable companies with positive growth)
  4. EV/EBITDA reasonableness (if available)
  5. Peer PE comparison (if available) — is the company cheaper or more expensive
     than the industry median?

Growth company handling:
  - If revenue growth > 15%, the company is classified as "growth"
  - Growth companies with PE < 0: SKIP (expected — investing in growth)
  - Growth companies with PE > 100: use PEG with relaxed threshold (PEG < 3)
  - Non-growth companies: strict PE checks as before

EV/EBITDA benchmarks:
  - < 10: attractive (PASS)
  - 10-20: reasonable (PASS)
  - 20-30: expensive but tolerable for growth (conditional PASS)
  - > 30: overvalued (FAIL)
  - negative EBITDA: SKIP

Peer PE comparison (Check 5):
  - peer_median_pe: median PE of comparable industry peers (positive PE only)
  - Company PE <= median: PASS (cheaper than peers)
  - Company PE in (median, median*1.5]: marginal (discount for growth companies)
  - Company PE > median*1.5: FAIL (expensive vs peers)
  - If peer data unavailable: SKIP

Scoring: all pass=5, 1 fail=4, 2 fail=3, all fail=1
"""


def score(data: dict) -> dict:
    """Score valuation with growth-aware PE assessment and EV/EBITDA.

    Args:
        data: dict with keys 'pe_ratio', 'pe_history_percentile',
              'revenue_growth_rate' (as percentage, e.g. 25 for 25%),
              'ev_to_ebitda', 'ebitda', 'market_cap'

    Returns:
        dict with 'score' (int 0-5) and 'details' (list of str)
    """
    details = []
    checks_passed = 0
    total_checks = 0

    pe_ratio = data.get("pe_ratio")
    rev_growth = data.get("revenue_growth_rate", 0)  # percentage
    is_growth = rev_growth > 15  # >15% revenue growth = growth company

    if is_growth:
        details.append(f"company type: growth (revenue +{rev_growth:.1f}%)")

    # Check 1: PE reasonableness (growth-aware)
    if pe_ratio is not None:
        total_checks += 1
        if pe_ratio <= 0:
            if is_growth:
                # Growth company not yet profitable — expected, not a failure
                details.append(f"pe_ratio: {pe_ratio:.2f} <= 0 (亏损, 但高增长 +{rev_growth:.1f}%) - SKIP")
                total_checks -= 1  # don't count this check
            else:
                details.append(f"pe_ratio: {pe_ratio:.2f} <= 0 (亏损, 增长 {rev_growth:.1f}%) - FAIL")
        elif pe_ratio < 100:
            details.append(f"pe_ratio: {pe_ratio:.2f} in (0, 100) - PASS")
            checks_passed += 1
        else:
            # PE >= 100: check if growth justifies it
            if is_growth and rev_growth > 0:
                peg = pe_ratio / rev_growth
                if peg < 3.0:
                    details.append(f"pe_ratio: {pe_ratio:.2f} >= 100, 但 PEG={peg:.2f} < 3 (高增长可接受) - PASS")
                    checks_passed += 1
                else:
                    details.append(f"pe_ratio: {pe_ratio:.2f} >= 100, PEG={peg:.2f} >= 3 - FAIL")
            else:
                details.append(f"pe_ratio: {pe_ratio:.2f} >= 100 (非成长型) - FAIL")
    else:
        details.append("pe_ratio: missing - SKIP")

    # Check 2: PE_history_percentile < 0.70 (skip if None)
    pe_hist_pct = data.get("pe_history_percentile")
    if pe_hist_pct is not None:
        total_checks += 1
        if pe_hist_pct < 0.70:
            details.append(f"pe_history_percentile: {pe_hist_pct:.2f} < 0.70 - PASS")
            checks_passed += 1
        else:
            details.append(f"pe_history_percentile: {pe_hist_pct:.2f} >= 0.70 - FAIL")
    else:
        details.append("pe_history_percentile: not provided - SKIP")

    # Check 3: PEG < 2.0 (only for profitable companies with meaningful growth)
    if pe_ratio is not None and pe_ratio > 0 and not is_growth:
        # Non-growth company: standard PEG check
        if rev_growth > 1:
            peg = pe_ratio / rev_growth
            total_checks += 1
            if peg < 2.0:
                details.append(f"peg_ratio: {peg:.2f} < 2.0 (PE/{rev_growth:.1f}%) - PASS")
                checks_passed += 1
            else:
                details.append(f"peg_ratio: {peg:.2f} >= 2.0 - FAIL")
        else:
            details.append(f"peg_ratio: skipped (growth {rev_growth:.1f}% <= 1%) - SKIP")
    elif is_growth and pe_ratio is not None and pe_ratio > 0:
        # Growth company: relaxed PEG already handled in Check 1
        details.append("peg_ratio: already assessed in PE check for growth company - SKIP")
    else:
        details.append("peg_ratio: skipped (PE <= 0 or missing) - SKIP")

    # Check 4: EV/EBITDA (if available)
    ev_to_ebitda = data.get("ev_to_ebitda")
    ebitda = data.get("ebitda")
    if ev_to_ebitda is not None and ebitda is not None and ebitda > 0:
        total_checks += 1
        if ev_to_ebitda < 10:
            details.append(f"ev_to_ebitda: {ev_to_ebitda:.1f}x < 10x (有吸引力) - PASS")
            checks_passed += 1
        elif ev_to_ebitda < 20:
            details.append(f"ev_to_ebitda: {ev_to_ebitda:.1f}x in [10, 20) (合理) - PASS")
            checks_passed += 1
        elif ev_to_ebitda < 30:
            if is_growth:
                details.append(f"ev_to_ebitda: {ev_to_ebitda:.1f}x in [20, 30) (偏贵但成长型可接受) - PASS")
                checks_passed += 1
            else:
                details.append(f"ev_to_ebitda: {ev_to_ebitda:.1f}x in [20, 30) (偏贵) - FAIL")
        else:
            details.append(f"ev_to_ebitda: {ev_to_ebitda:.1f}x >= 30x (高估) - FAIL")
    elif ebitda is not None and ebitda <= 0:
        details.append(f"ev_to_ebitda: SKIP (EBITDA={ebitda:.0f} <= 0)")
    else:
        details.append("ev_to_ebitda: data unavailable - SKIP")

    # Check 5: Peer PE comparison
    peer_median_pe = data.get("peer_median_pe")
    if peer_median_pe is not None and peer_median_pe > 0 and pe_ratio is not None and pe_ratio > 0:
        total_checks += 1
        premium = (pe_ratio - peer_median_pe) / peer_median_pe
        if pe_ratio <= peer_median_pe:
            details.append(f"peer_pe: PE {pe_ratio:.1f}x <= 行业中位数 {peer_median_pe:.1f}x (便宜) - PASS")
            checks_passed += 1
        elif premium <= 0.50:
            if is_growth:
                details.append(f"peer_pe: PE {pe_ratio:.1f}x vs 行业中位数 {peer_median_pe:.1f}x (+{premium:.0%} 溢价, 成长型可接受) - PASS")
                checks_passed += 1
            else:
                details.append(f"peer_pe: PE {pe_ratio:.1f}x vs 行业中位数 {peer_median_pe:.1f}x (+{premium:.0%} 溢价) - FAIL")
        else:
            details.append(f"peer_pe: PE {pe_ratio:.1f}x vs 行业中位数 {peer_median_pe:.1f}x (+{premium:.0%} 显著溢价) - FAIL")
    elif peer_median_pe is not None:
        details.append("peer_pe: data available but PE missing or <= 0 - SKIP")
    else:
        details.append("peer_pe: no peer data provided - SKIP")

    # Avoid division by zero
    if total_checks == 0:
        return {"score": 3, "details": details + ["No scorable checks - neutral score"]}

    failures = total_checks - checks_passed
    score_map = {0: 5, 1: 4, 2: 3, 3: 1}
    final_score = score_map.get(failures, 0)

    return {"score": final_score, "details": details}
