"""Profitability analysis module.

Checks:
  1. revenue_growth > 0.08
  2. gross_margin > 0.15 (industry median default)
  3. net_margin > 0.05
  4. ROE > 0.10
  5. profit quality: net_income_growth vs revenue_growth

Profit quality:
  - profit growth > revenue growth → 高质量 (利润增长快于营收，经营杠杆/成本优化)
  - profit growth < revenue growth → 较低质量 (增收不增利，可能靠烧钱换增长)
  - profit growth and revenue growth both negative → 不评分

Special handling:
  - 亏损 (net_margin < 0): extra penalty (-1) — worse than low-margin profitable
  - 资不抵债 (total_equity <= 0): ROE FAIL

Scoring:
  base = {0 fail: 5, 1 fail: 4, 2 fail: 3, 3 fail: 2, 4 fail: 0, 5 fail: 0}
  final = max(0, base - loss_penalty + quality_bonus)
"""
from __future__ import annotations


def score(data: dict) -> dict:
    """Score profitability based on revenue growth, margins, ROE, and profit quality.

    Args:
        data: dict with keys:
            'revenue_growth' — latest YoY revenue growth rate
            'gross_margin' — latest gross margin
            'net_margin' — latest net margin
            'roe' — latest ROE
            'industry_median_gross_margin' (optional)
            'net_income_growth' (optional) — latest YoY net income growth rate
            'revenue_growth_rates' (optional) — multi-year revenue growth rates
            'net_income_growth_rates' (optional) — multi-year net income growth rates

    Returns:
        dict with 'score' (int 0-5) and 'details' (list of str)
    """
    details = []
    checks_passed = 0
    total_checks = 4

    rev_growth = data.get("revenue_growth", 0)
    gross_margin = data.get("gross_margin", 0)
    net_margin = data.get("net_margin", 0)
    roe = data.get("roe", 0)
    is_loss = net_margin < 0

    # Check 1: revenue_growth > 0.08
    if rev_growth > 0.08:
        details.append(f"revenue_growth: {rev_growth:.2%} > 8% - PASS")
        checks_passed += 1
    else:
        details.append(f"revenue_growth: {rev_growth:.2%} <= 8% - FAIL")

    # Check 2: gross_margin > industry_median (default 0.15)
    industry_median = data.get("industry_median_gross_margin", 0.15)
    if gross_margin > industry_median:
        details.append(f"gross_margin: {gross_margin:.2%} > {industry_median:.2%} - PASS")
        checks_passed += 1
    else:
        details.append(f"gross_margin: {gross_margin:.2%} <= {industry_median:.2%} - FAIL")

    # Check 3: net_margin > 0.05
    if net_margin > 0.05:
        details.append(f"net_margin: {net_margin:.2%} > 5% - PASS")
        checks_passed += 1
    else:
        details.append(f"net_margin: {net_margin:.2%} <= 5% - FAIL")

    # Check 4: ROE > 0.10
    # 亏损公司ROE不具参考意义，直接FAIL
    if is_loss:
        details.append(f"roe: {roe:.2%} — 亏损公司ROE不具参考意义 - FAIL")
    elif roe > 0.10:
        details.append(f"roe: {roe:.2%} > 10% - PASS")
        checks_passed += 1
    else:
        details.append(f"roe: {roe:.2%} <= 10% - FAIL")

    failures = total_checks - checks_passed
    score_map = {0: 5, 1: 4, 2: 3, 3: 2, 4: 0, 5: 0}
    base_score = score_map.get(failures, 0)

    # 亏损惩罚: 亏损比低毛利更严重，额外扣1分
    loss_penalty = 1 if is_loss and base_score > 0 else 0
    final_score = base_score - loss_penalty

    if loss_penalty:
        details.append(f"loss_penalty: 亏损公司额外 -1 (base {base_score} -> {final_score})")

    # Check 5: Profit quality — revenue growth vs net income growth
    ni_growth = data.get("net_income_growth")
    ni_growth_rates = data.get("net_income_growth_rates", [])
    rev_growth_rates = data.get("revenue_growth_rates", [])

    # Use latest period for quality check
    if ni_growth is not None and rev_growth is not None:
        # Only assess quality when both are meaningful
        if rev_growth > 0 and ni_growth > 0:
            if ni_growth > rev_growth:
                quality_bonus = 1
                details.append(f"利润质量: 利润增长({ni_growth:.1%}) > 营收增长({rev_growth:.1%}) - 高质量 +1")
            else:
                quality_bonus = 0
                details.append(f"利润质量: 利润增长({ni_growth:.1%}) <= 营收增长({rev_growth:.1%}) - 较低质量")
        elif rev_growth > 0 and ni_growth <= 0:
            quality_bonus = -1
            details.append(f"利润质量: 营收增({rev_growth:.1%})但利润降({ni_growth:.1%}) - 增收不增利 -1")
        elif rev_growth <= 0 and ni_growth > 0:
            quality_bonus = 0
            details.append(f"利润质量: 营收降({rev_growth:.1%})但利润增({ni_growth:.1%}) - 可能不可持续")
        else:
            quality_bonus = 0
            details.append(f"利润质量: 营收({rev_growth:.1%})和利润({ni_growth:.1%})均下降 - SKIP")
    else:
        quality_bonus = 0
        details.append("利润质量: 缺少利润增长率数据 - SKIP")

    final_score = max(0, min(5, final_score + quality_bonus))
    if quality_bonus != 0:
        details.append(f"quality_adj: {quality_bonus:+d} -> final {final_score}")

    return {"score": final_score, "details": details}
