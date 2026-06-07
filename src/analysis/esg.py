"""Simplified ESG (governance) scoring module.

Checks four governance indicators and produces a score 0-5 with details.
All fields are optional — missing data yields a neutral score of 3.

Indicators:
  1. related_party_transactions : ratio to revenue (0 = best, >10% = concern)
  2. independent_director_ratio : fraction of independent directors (>1/3 = good)
  3. audit_opinion              : 'unqualified' / 'qualified' / 'adverse'
  4. insider_ownership_pct      : insider holding % (moderate 5-30% = good)
"""


def score_governance(data: dict) -> dict:
    """Score corporate governance from a data dict.

    Parameters
    ----------
    data : dict
        Optional keys (all missing → neutral score 3):
        - ``related_party_transactions`` (float) — ratio to revenue, e.g. 0.05 for 5%
        - ``independent_director_ratio`` (float) — fraction, e.g. 0.4 for 40%
        - ``audit_opinion`` (str) — one of 'unqualified', 'qualified', 'adverse'
        - ``insider_ownership_pct`` (float) — percentage, e.g. 15 for 15%

    Returns
    -------
    dict
        ``score`` (int 0-5) and ``details`` (list of str).
    """
    sub_scores: list[float] = []
    details: list[str] = []

    # --- 1. Related-party transactions -----------------------------------
    rpt = data.get("related_party_transactions")
    if rpt is not None:
        if rpt <= 0:
            sub_scores.append(5.0)
            details.append(f"related_party_transactions: {rpt:.2%} (无关联交易) — PASS")
        elif rpt <= 0.03:
            sub_scores.append(4.0)
            details.append(f"related_party_transactions: {rpt:.2%} (≤3%, 低风险) — PASS")
        elif rpt <= 0.10:
            sub_scores.append(3.0)
            details.append(f"related_party_transactions: {rpt:.2%} (3-10%, 一般) — NEUTRAL")
        else:
            sub_scores.append(1.0)
            details.append(
                f"related_party_transactions: {rpt:.2%} (>10%, 关注) — FAIL"
            )
    else:
        details.append("related_party_transactions: 未提供 — SKIP (neutral 3)")
        sub_scores.append(3.0)

    # --- 2. Independent director ratio -----------------------------------
    idr = data.get("independent_director_ratio")
    if idr is not None:
        if idr >= 0.5:
            sub_scores.append(5.0)
            details.append(
                f"independent_director_ratio: {idr:.0%} (≥50%, 优秀) — PASS"
            )
        elif idr >= 1 / 3:
            sub_scores.append(4.0)
            details.append(
                f"independent_director_ratio: {idr:.0%} (≥1/3, 合规) — PASS"
            )
        elif idr >= 0.25:
            sub_scores.append(2.5)
            details.append(
                f"independent_director_ratio: {idr:.0%} (<1/3, 偏低) — FAIL"
            )
        else:
            sub_scores.append(1.0)
            details.append(
                f"independent_director_ratio: {idr:.0%} (<25%, 严重不足) — FAIL"
            )
    else:
        details.append("independent_director_ratio: 未提供 — SKIP (neutral 3)")
        sub_scores.append(3.0)

    # --- 3. Audit opinion -----------------------------------------------
    ao = data.get("audit_opinion")
    if ao is not None:
        ao_lower = ao.strip().lower()
        if ao_lower == "unqualified":
            sub_scores.append(5.0)
            details.append("audit_opinion: unqualified (标准无保留) — PASS")
        elif ao_lower == "qualified":
            sub_scores.append(2.0)
            details.append("audit_opinion: qualified (保留意见) — FAIL")
        elif ao_lower == "adverse":
            sub_scores.append(0.0)
            details.append("audit_opinion: adverse (否定意见) — FAIL")
        elif ao_lower == "emphasis":
            # Some systems distinguish "emphasis of matter" — mildly negative.
            sub_scores.append(3.5)
            details.append("audit_opinion: emphasis (带强调事项段) — NEUTRAL")
        else:
            sub_scores.append(3.0)
            details.append(f"audit_opinion: '{ao}' (未知类型) — SKIP (neutral 3)")
    else:
        details.append("audit_opinion: 未提供 — SKIP (neutral 3)")
        sub_scores.append(3.0)

    # --- 4. Insider ownership percentage ---------------------------------
    insider = data.get("insider_ownership_pct")
    if insider is not None:
        if 5 <= insider <= 30:
            sub_scores.append(5.0)
            details.append(
                f"insider_ownership_pct: {insider:.1f}% (5-30%, 适度) — PASS"
            )
        elif insider < 5:
            sub_scores.append(3.0)
            details.append(
                f"insider_ownership_pct: {insider:.1f}% (<5%, 偏低) — NEUTRAL"
            )
        elif insider <= 50:
            sub_scores.append(3.5)
            details.append(
                f"insider_ownership_pct: {insider:.1f}% (30-50%, 偏高但可接受) — NEUTRAL"
            )
        else:
            sub_scores.append(2.0)
            details.append(
                f"insider_ownership_pct: {insider:.1f}% (>50%, 过度集中) — FAIL"
            )
    else:
        details.append("insider_ownership_pct: 未提供 — SKIP (neutral 3)")
        sub_scores.append(3.0)

    # --- Aggregate -------------------------------------------------------
    avg = sum(sub_scores) / len(sub_scores) if sub_scores else 3.0
    final_score = int(round(avg))
    final_score = max(0, min(5, final_score))

    return {"score": final_score, "details": details}
