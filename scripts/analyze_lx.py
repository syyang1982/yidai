"""乐信 (LX) 手动分析 — 基于 FY2025 年报数据"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis import profitability, health, cashflow, valuation, growth
from src.data.models import _compute_grade, _compute_signal
from src.knowledge.base import KnowledgeBase
from src.data.store import YidaiStore

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai.duckdb")

# FY2025 数据 (单位: 百万人民币)
rev_2025 = 13_152
rev_2024 = 14_204
ni_2025 = 1_677
ni_2024 = 1_100
gp_2025 = 4_469
ta_2025 = 23_163
tl_2025 = 11_210
te_2025 = 11_953
ocf_2025 = 3_614
fcf_2025 = 3_262

price_usd = 2.45
pe = 2.04
rev_growth = (rev_2025 - rev_2024) / rev_2024  # -7.4%

print("=" * 55)
print("  乐信 (LX) — 手动七维分析")
print("=" * 55)
print(f"\n  FY2025 数据:")
print(f"  营收: {rev_2025/1e4:.1f}亿 (YoY {rev_growth*100:+.1f}%)")
print(f"  净利: {ni_2025/1e4:.1f}亿 (YoY +{(ni_2025/ni_2024-1)*100:.0f}%)")
print(f"  毛利率: {gp_2025/rev_2025*100:.1f}%")
print(f"  净利率: {ni_2025/rev_2025*100:.1f}%")
print(f"  ROE: {ni_2025/te_2025*100:.1f}%")
print(f"  负债率: {tl_2025/ta_2025*100:.1f}%")
print(f"  经营现金流: {ocf_2025/1e4:.1f}亿")
print(f"  自由现金流: {fcf_2025/1e4:.1f}亿")
print(f"  价格: ${price_usd}  PE: {pe}  股息率: 15.6%")

# 评分
prof = profitability.score({
    "revenue_growth": rev_growth,
    "gross_margin": gp_2025 / rev_2025,
    "net_margin": ni_2025 / rev_2025,
    "roe": ni_2025 / te_2025,
})
h = health.score({"debt_ratio": tl_2025 / ta_2025})
cf = cashflow.score({
    "operating_cash_flow": ocf_2025,
    "ocf_to_ni_ratio": ocf_2025 / ni_2025,
    "free_cash_flow": fcf_2025,
})
v = valuation.score({
    "pe_ratio": pe,
    "pe_history_percentile": None,
    "revenue_growth_rate": rev_growth * 100,
})
g = growth.score({
    "revenue_growth_rates": [rev_growth],
    "growth_drivers": ["消费信贷", "AI风控"],
})

scores = {
    "profitability": prof["score"], "health": h["score"],
    "cashflow": cf["score"], "valuation": v["score"],
    "growth": g["score"], "ownership": 4, "strategy": 4,
}
total = sum(scores.values())
grade = _compute_grade(total)
sig = _compute_signal(total, *scores.values())

# 打印
dim_cn = {"profitability": "盈利能力", "health": "财务健康", "cashflow": "现金流",
          "valuation": "估值", "growth": "增长质量", "ownership": "股权结构", "strategy": "公司战略"}
print(f"\n  七维评分:")
for dim, cn in dim_cn.items():
    s = scores[dim]
    bar = "█" * s + "░" * (5 - s)
    print(f"  {cn:　<6} [{bar}] {s}/5")

emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(sig, "❓")
print(f"\n  总分: {total}/35  等级: {grade}  信号: {emoji} {sig}")

# 详情
for name, d in [("盈利能力", prof), ("财务健康", h), ("现金流", cf), ("估值", v), ("增长", g)]:
    for line in d.get("details", []):
        print(f"    {line}")

# 知识库
kb = KnowledgeBase()
kb.create_company_profile(
    ticker="LX", name="乐信", market="US", sector="金融科技/消费信贷",
    thesis="中国领先消费金融科技平台。AI风控能力强，资产质量改善。PE仅2倍，股息率15.6%，极度低估。净利增长52%，现金流暴增234%。"
)
kb.update_company_scores("LX", {
    '盈利': scores['profitability'], '健康': scores['health'],
    '现金流': scores['cashflow'], '估值': scores['valuation'],
    '成长': scores['growth'], '股东': scores['ownership'], '战略': scores['strategy'],
})
kb.update_company_financials("LX", {
    '营收': f'{rev_2025/1e4:.1f}亿', '净利': f'{ni_2025/1e4:.1f}亿',
    'ROE': f'{ni_2025/te_2025*100:.1f}%', '毛利率': f'{gp_2025/rev_2025*100:.1f}%',
    '净利率': f'{ni_2025/rev_2025*100:.1f}%', '负债率': f'{tl_2025/ta_2025*100:.1f}%',
    'PE': f'{pe:.1f}',
})
for risk in ["信贷周期风险（经济下行时坏账上升）", "监管政策变化（金融科技监管）",
             "营收下滑趋势(-7.4%)能否扭转", "中美关系对中概股的影响",
             "高股息率是否可持续"]:
    kb.add_risk("LX", risk)

kb.add_lesson("PE<5 + ROE>10% + 股息率>10% 可能是深度价值陷阱也可能是金矿，需要看现金流和资产质量", "LX", "估值")
kb.add_lesson("金融科技公司OCF远超NI是正常模式（利息收入的现金回收），不能用OCF/NI比简单判断", "LX", "现金流")

# DuckDB
store = YidaiStore(DB_PATH)
store.upsert_company({"ticker": "LX", "name": "乐信", "market": "US",
                      "currency": "USD", "sector": "金融科技/消费信贷"})
store.close()

print(f"\n  ✅ 已存入知识库: knowledge/companies/LX.md")
print(f"\n  独特之处:")
print(f"  · PE仅2倍 — 10家公司中最低")
print(f"  · 股息率15.6% — 10家公司中最高")
print(f"  · 净利增长52% — 利润在改善")
print(f"  · 现金流暴增234% — 现金回收强劲")
print(f"  · 但营收下滑7.4% — 增长是隐忧")
