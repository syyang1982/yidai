"""Multi-master investment framework integration module.

Synthesizes insights from 8 investment masters into a unified assessment
layer on top of yidai's 8-dimension scoring system.

Masters integrated:
  1. Buffett    — moat, margin of safety, management quality
  2. Lynch      — stock categorization, PEG, tenbagger traits
  3. Marks      — market cycles, second-level thinking, risk
  4. Munger     — mental models, inversion, pre-mortem
  5. Graham     — defensive investor criteria, Mr. Market
  6. Greenblatt — magic formula (ROIC + earnings yield)
  7. 段永平      — 好生意+好公司+好价格, 本分
  8. 李录       — 知识的诚实, 中国市场特殊性

This module does NOT replace individual master skills — it provides
the glue layer that combines their outputs into a single integrated
assessment for the user's personal investment style.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# 1. 林奇分类 (Lynch Classification)
# ---------------------------------------------------------------------------

def classify_lynch_type(scores: dict, financial_data: dict = None) -> dict:
    """Classify stock into Lynch's 6 categories based on yidai scores.

    Args:
        scores: dict with yidai dimension scores (profitability, health, etc.)
        financial_data: optional dict with revenue_growth_rate, dividend_yield, etc.

    Returns:
        dict with category, description, valuation_method, strategy
    """
    growth = scores.get("growth", 0)
    health = scores.get("health", 0)
    valuation = scores.get("valuation", 0)
    dividend = scores.get("dividend", 0)
    profitability = scores.get("profitability", 0)

    rev_growth = (financial_data or {}).get("revenue_growth_rate", 0)

    if growth >= 4:
        return {
            "category": "快速增长型",
            "category_en": "Fast Grower",
            "description": f"年增长率 >20%，十倍股摇篮",
            "valuation_method": "PEG < 1",
            "strategy": "重仓持有，关注增长持续性",
            "tenbagger_potential": True,
        }

    if growth == 3 and health >= 3 and profitability >= 3:
        return {
            "category": "稳健增长型",
            "category_en": "Stalwart",
            "description": "年增长率 10-15%，大型知名公司",
            "valuation_method": "PE < 行业均值 + 分红稳定",
            "strategy": "经济下行时的安全港，反弹时涨20-50%",
            "tenbagger_potential": False,
        }

    if growth <= 2 and dividend >= 3:
        return {
            "category": "缓慢增长型",
            "category_en": "Slow Grower",
            "description": "年增长率 2-5%，主要靠分红",
            "valuation_method": "股息率 > 无风险利率",
            "strategy": "防御型配置，分红再投资",
            "tenbagger_potential": False,
        }

    # Check for turnaround signals (health improving)
    if health <= 2 and profitability >= 2:
        return {
            "category": "困境反转型",
            "category_en": "Turnaround",
            "description": "曾陷入困境但正在复苏",
            "valuation_method": "现金流转正 + 负债率下降",
            "strategy": "高风险高回报，需确认困境原因已消除",
            "tenbagger_potential": True,
        }

    return {
        "category": "待分类",
        "category_en": "Unclassified",
        "description": "需人工判断（周期型/资产隐蔽型）",
        "valuation_method": "PE历史分位 + 资产重估",
        "strategy": "深入研究后决定",
        "tenbagger_potential": False,
    }


# ---------------------------------------------------------------------------
# 2. PEG计算 (Lynch's Core Metric)
# ---------------------------------------------------------------------------

def calculate_peg(pe_ratio: Optional[float],
                  revenue_growth_rate: Optional[float],
                  earnings_growth_rate: Optional[float] = None) -> dict:
    """Calculate PEG ratio using Lynch's method.

    Uses revenue growth as primary (more stable), falls back to earnings growth.

    Args:
        pe_ratio: trailing PE
        revenue_growth_rate: as percentage (e.g. 25 for 25%)
        earnings_growth_rate: as percentage, fallback

    Returns:
        dict with peg, rating, source
    """
    growth = revenue_growth_rate or earnings_growth_rate
    source = "revenue" if revenue_growth_rate else "earnings"

    if pe_ratio is None or growth is None or growth <= 0:
        return {"peg": None, "rating": "无法计算", "source": source}

    peg = pe_ratio / growth

    if peg < 0.5:
        rating = "严重低估"
    elif peg < 1.0:
        rating = "合理偏低"
    elif peg < 1.5:
        rating = "合理"
    elif peg < 2.0:
        rating = "偏高"
    else:
        rating = "高估"

    return {"peg": round(peg, 2), "rating": rating, "source": source}


# ---------------------------------------------------------------------------
# 3. 格雷厄姆 PE×PB 检查
# ---------------------------------------------------------------------------

def graham_pe_x_pb(pe_ratio: Optional[float],
                   pb_ratio: Optional[float]) -> dict:
    """Graham's classic PE × PB ≤ 22.5 screening formula.

    Returns:
        dict with pe_x_pb, passes (bool), rating
    """
    if pe_ratio is None or pb_ratio is None:
        return {"pe_x_pb": None, "passes": None, "rating": "数据不足"}

    product = pe_ratio * pb_ratio

    if product <= 11.25:
        rating = "深度低估"
    elif product <= 22.5:
        rating = "合理偏低"
    elif product <= 33.75:
        rating = "合理"
    else:
        rating = "偏贵"

    return {
        "pe_x_pb": round(product, 1),
        "passes": product <= 22.5,
        "rating": rating,
    }


# ---------------------------------------------------------------------------
# 4. 格林布拉特 神奇公式 (Magic Formula)
# ---------------------------------------------------------------------------

def greenblatt_assessment(ebit: Optional[float], ev: Optional[float],
                          invested_capital: Optional[float],
                          tax_rate: float = 0.25) -> dict:
    """Calculate Greenblatt's Magic Formula metrics.

    Args:
        ebit: Earnings Before Interest and Taxes
        ev: Enterprise Value (market_cap + net_debt)
        invested_capital: Total assets - non-interest current liabilities - cash
        tax_rate: effective tax rate

    Returns:
        dict with roic, earnings_yield, rating
    """
    roic = None
    earnings_yield = None

    if ebit is not None and invested_capital and invested_capital > 0:
        roic = ebit * (1 - tax_rate) / invested_capital

    if ebit is not None and ev and ev > 0:
        earnings_yield = ebit / ev

    # Rating
    roic_ok = roic is not None and roic > 0.15
    ey_ok = earnings_yield is not None and earnings_yield > 0.07

    if roic_ok and ey_ok:
        rating = "✅ 好公司+好价格"
    elif roic_ok:
        rating = "⚠️ 好公司但偏贵"
    elif ey_ok:
        rating = "⚠️ 便宜但质量待验证"
    else:
        rating = "❌ 不符合神奇公式"

    return {
        "roic": round(roic, 4) if roic else None,
        "roic_pct": f"{roic*100:.1f}%" if roic else "N/A",
        "earnings_yield": round(earnings_yield, 4) if earnings_yield else None,
        "earnings_yield_pct": f"{earnings_yield*100:.1f}%" if earnings_yield else "N/A",
        "roic_pass": roic_ok,
        "ey_pass": ey_ok,
        "rating": rating,
    }


# ---------------------------------------------------------------------------
# 5. 段永平三维评估
# ---------------------------------------------------------------------------

def duanyongping_checklist(scores: dict, qualitative: dict = None) -> dict:
    """段永平 好生意+好公司+好价格 三维评估。

    Args:
        scores: yidai dimension scores
        qualitative: optional dict with moat_rating, management_rating, etc.

    Returns:
        dict with three dimensions + overall verdict
    """
    qual = qualitative or {}

    # 好生意 (from profitability + growth + cashflow)
    good_business_score = (
        scores.get("profitability", 0) +
        scores.get("growth", 0) +
        scores.get("cashflow", 0)
    ) / 3

    # 好公司 (from health + ownership + strategy)
    good_company_score = (
        scores.get("health", 0) +
        scores.get("ownership", 3) +
        scores.get("strategy", 3)
    ) / 3

    # 好价格 (from valuation + dividend)
    good_price_score = (
        scores.get("valuation", 0) +
        scores.get("dividend", 0)
    ) / 2

    # Moat from qualitative if available
    moat = qual.get("moat_rating", 3)

    # Verdict
    if good_business_score >= 4 and good_company_score >= 3.5 and good_price_score >= 3.5:
        verdict = "✅ 好生意+好公司+好价格 — 强烈推荐"
    elif good_business_score >= 3.5 and good_company_score >= 3:
        if good_price_score < 3:
            verdict = "⏳ 好生意+好公司，等待好价格"
        else:
            verdict = "✅ 基本符合 — 值得持有"
    elif good_business_score < 3:
        verdict = "❌ 生意模式不够好"
    elif good_company_score < 2.5:
        verdict = "❌ 公司治理有问题"
    else:
        verdict = "⚠️ 需要深入研究"

    return {
        "good_business": round(good_business_score, 1),
        "good_company": round(good_company_score, 1),
        "good_price": round(good_price_score, 1),
        "moat_rating": moat,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# 6. 芒格 Pre-mortem
# ---------------------------------------------------------------------------

def generate_premortem_questions(scores: dict, lynch_type: dict = None) -> list[str]:
    """Generate pre-mortem questions based on the company's risk profile.

    Returns list of questions tailored to the specific investment.
    """
    questions = []

    # Universal questions
    questions.append("假设一年后亏损50%，最可能的原因是什么？")
    questions.append("管理层有没有欺骗的动机和历史？")
    questions.append("这个行业会不会在10年内消失？")

    # Score-based specific questions
    if scores.get("valuation", 0) >= 4:
        questions.append("估值低是否因为市场看到了我没看到的风险？（价值陷阱？）")

    if scores.get("growth", 0) >= 4:
        questions.append("高增长能持续多久？增长率下降时估值会怎样？")

    if scores.get("health", 0) <= 2:
        questions.append("财务健康恶化是暂时的还是结构性的？")

    if scores.get("cashflow", 0) <= 2:
        questions.append("现金流为负是因为扩张还是商业模式本身不赚钱？")

    # Lynch-type specific
    if lynch_type:
        cat = lynch_type.get("category", "")
        if cat == "困境反转型":
            questions.append("困境是否真的已经结束？还是会继续恶化？")
        elif cat == "快速增长型":
            questions.append("增长是靠烧钱还是靠内生？竞争对手在追赶吗？")
        elif cat == "周期型":
            questions.append("我们是在周期的哪个位置？PE低是否因为周期顶部？")

    # Munger's inversion
    questions.append("反对这笔投资的最强论据是什么？")
    questions.append("我是否因为FOMO/锚定/确认偏差才想买？")

    return questions


# ---------------------------------------------------------------------------
# 7. 综合评估 (Master Integration)
# ---------------------------------------------------------------------------

def integrated_assessment(
    yidai_scores: dict,
    financial_data: dict = None,
    price_data: dict = None,
    qualitative: dict = None,
) -> dict:
    """Run all master frameworks and produce a unified assessment.

    Args:
        yidai_scores: dict with dimension scores from yidai scoring
        financial_data: optional financial statement data
        price_data: optional market price data
        qualitative: optional qualitative data (moat, management, etc.)

    Returns:
        dict with all master assessments + integrated verdict
    """
    fin = financial_data or {}
    price = price_data or {}
    qual = qualitative or {}

    # 1. Lynch classification
    lynch = classify_lynch_type(yidai_scores, fin)

    # 2. PEG
    peg = calculate_peg(
        price.get("pe_ratio"),
        fin.get("revenue_growth_rate"),
        fin.get("earnings_growth_rate"),
    )

    # 3. Graham PE×PB
    graham = graham_pe_x_pb(price.get("pe_ratio"), price.get("pb_ratio"))

    # 4. Greenblatt (if data available)
    greenblatt = greenblatt_assessment(
        ebit=fin.get("ebit") or fin.get("operating_income"),
        ev=price.get("ev"),
        invested_capital=fin.get("invested_capital"),
    )

    # 5. 段永平
    dyp = duanyongping_checklist(yidai_scores, qual)

    # 6. Pre-mortem questions
    premortem = generate_premortem_questions(yidai_scores, lynch)

    # 7. Integrated verdict
    total = sum(yidai_scores.get(k, 0) for k in [
        "profitability", "health", "cashflow", "valuation",
        "growth", "dividend", "ownership", "strategy"
    ])

    # Check for dealbreakers
    dealbreakers = []
    if yidai_scores.get("health", 0) < 2:
        dealbreakers.append("财务健康严重不足")
    if yidai_scores.get("cashflow", 0) < 2:
        dealbreakers.append("现金流严重不足")
    if not qual.get("circle_of_competence", True):
        dealbreakers.append("不在能力圈内")

    # Final verdict
    if dealbreakers:
        verdict = f"🚫 不建议投资: {'; '.join(dealbreakers)}"
    elif total >= 30 and peg.get("peg") and peg["peg"] < 1:
        verdict = "🟢 强买入 — 高质量+低估值"
    elif total >= 25 and dyp["good_business"] >= 4:
        verdict = "🟢 买入 — 优质公司合理价格"
    elif total >= 22:
        verdict = "🟡 持有 — 基本面良好"
    elif total >= 17:
        verdict = "🔵 观望 — 需要更好价格或更强基本面"
    else:
        verdict = "🔴 回避 — 综合质量不足"

    return {
        "lynch": lynch,
        "peg": peg,
        "graham": graham,
        "greenblatt": greenblatt,
        "duanyongping": dyp,
        "premortem_questions": premortem,
        "yidai_total": total,
        "dealbreakers": dealbreakers,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# 8. 格式化输出
# ---------------------------------------------------------------------------

def format_integrated_assessment(result: dict) -> str:
    """Format integrated assessment for terminal display."""
    lines = []

    lines.append("  ═══════════════════════════════════════")
    lines.append("  📊 综合投资框架评估")
    lines.append("  ═══════════════════════════════════════")

    # Lynch
    lynch = result.get("lynch", {})
    lines.append(f"\n  【林奇分类】 {lynch.get('category', '?')} ({lynch.get('category_en', '?')})")
    lines.append(f"    {lynch.get('description', '')}")
    lines.append(f"    估值方法: {lynch.get('valuation_method', '')}")

    # PEG
    peg = result.get("peg", {})
    if peg.get("peg") is not None:
        lines.append(f"\n  【PEG估值】 {peg['peg']:.2f} — {peg['rating']} (基于{peg.get('source', '?')}增长)")
    else:
        lines.append(f"\n  【PEG估值】 {peg.get('rating', '无法计算')}")

    # Graham
    graham = result.get("graham", {})
    if graham.get("pe_x_pb") is not None:
        check = "✅" if graham["passes"] else "❌"
        lines.append(f"\n  【格雷厄姆】 PE×PB = {graham['pe_x_pb']:.1f} {check} (≤22.5) — {graham['rating']}")

    # Greenblatt
    gb = result.get("greenblatt", {})
    lines.append(f"\n  【神奇公式】 ROIC={gb.get('roic_pct', 'N/A')}  收益率={gb.get('earnings_yield_pct', 'N/A')}")
    lines.append(f"    {gb.get('rating', '')}")

    # 段永平
    dyp = result.get("duanyongping", {})
    lines.append(f"\n  【段永平三维】 好生意={dyp.get('good_business', '?')} 好公司={dyp.get('good_company', '?')} 好价格={dyp.get('good_price', '?')}")
    lines.append(f"    {dyp.get('verdict', '')}")

    # Pre-mortem
    questions = result.get("premortem_questions", [])
    if questions:
        lines.append(f"\n  【Pre-mortem 事前验尸】")
        for i, q in enumerate(questions[:5], 1):
            lines.append(f"    {i}. {q}")

    # Dealbreakers
    if result.get("dealbreakers"):
        lines.append(f"\n  ⛔ 致命问题:")
        for db in result["dealbreakers"]:
            lines.append(f"    · {db}")

    # Final verdict
    lines.append(f"\n  ═══════════════════════════════════════")
    lines.append(f"  综合结论: {result.get('verdict', '?')}")
    lines.append(f"  意怠基础分: {result.get('yidai_total', '?')}/40")
    lines.append(f"  ═══════════════════════════════════════")

    return "\n".join(lines)
