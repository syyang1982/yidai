"""分析阿里巴巴 (9988.HK)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import EastmoneyFetcher
from src.data.store import YidaiStore
from src.analysis import profitability, health, cashflow, valuation, growth
from src.data.models import _compute_grade, _compute_signal
from src.knowledge.base import KnowledgeBase

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai.duckdb")

fetcher = EastmoneyFetcher()
kb = KnowledgeBase()

ticker = "09988"
display = "9988.HK"
name = "阿里巴巴"

print("=" * 55)
print(f"  {name} ({display})")
print("=" * 55)

# 拉取数据
all_fin = fetcher.fetch_financials(ticker, periods=10)
annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                key=lambda x: x["period"])
price = fetcher.fetch_price(ticker)

print(f"  年报: {len(annual)} 期")
print(f"  价格: {price.get('close_price', 'N/A')}  PE: {price.get('pe_ratio', 'N/A')}")

if len(annual) < 2:
    print("  ❌ 数据不足")
    sys.exit(1)

latest = annual[-1]
prev = annual[-2]

# 评分
revenue = latest.get("revenue", 0) or 0
denom = revenue if revenue else 1
prev_rev = prev.get("revenue", 0) or 0
rev_growth = (revenue - prev_rev) / prev_rev if prev_rev > 0 else 0

ta = latest.get("total_assets", 0) or 0
tl = latest.get("total_liabilities", 0) or 0

prof = profitability.score({
    "revenue_growth": rev_growth,
    "gross_margin": (latest.get("gross_profit", 0) or 0) / denom,
    "net_margin": (latest.get("net_income", 0) or 0) / denom,
    "roe": (latest.get("net_income", 0) or 0) / (latest.get("total_equity", 0) or 1),
})
h = health.score({"debt_ratio": tl / ta if ta > 0 else 0})

ocf = latest.get("operating_cash_flow", 0) or 0
ni = latest.get("net_income", 0) or 1
cf = cashflow.score({
    "operating_cash_flow": ocf,
    "ocf_to_ni_ratio": ocf / ni if ni else 0,
    "free_cash_flow": latest.get("free_cash_flow", 0) or 0,
})

pe = price.get("pe_ratio")
v = valuation.score({
    "pe_ratio": pe,
    "pe_history_percentile": None,
    "revenue_growth_rate": rev_growth * 100,
})

g = growth.score({
    "revenue_growth_rates": [rev_growth] if rev_growth else [],
    "growth_drivers": ["云计算", "电商", "国际业务"],
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
dim_names = {"profitability": "盈利能力", "health": "财务健康", "cashflow": "现金流",
             "valuation": "估值", "growth": "增长质量", "ownership": "股权结构", "strategy": "公司战略"}
print(f"\n  最新年报: {latest['period']}")
print(f"  营收: {revenue/1e8:.0f}亿  净利: {ni/1e8:.0f}亿")
for dim, name_cn in dim_names.items():
    s = scores[dim]
    bar = "█" * s + "░" * (5 - s)
    print(f"  {name_cn:　<6} [{bar}] {s}/5")

emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(sig, "❓")
print(f"\n  总分: {total}/35  等级: {grade}  信号: {emoji} {sig}")

gross_margin = (latest.get("gross_profit", 0) or 0) / denom
net_margin = (ni or 0) / denom
roe = (ni or 0) / (latest.get("total_equity", 0) or 1)
debt_ratio = tl / (ta or 1)

print(f"  毛利率: {gross_margin*100:.1f}%")
print(f"  净利率: {net_margin*100:.1f}%")
print(f"  ROE: {roe*100:.1f}%")
print(f"  负债率: {debt_ratio*100:.1f}%")
print(f"  经营现金流: {ocf/1e8:.0f}亿")

# 评分详情
all_details = [
    ("盈利能力", prof), ("财务健康", h), ("现金流", cf), ("估值", v), ("增长", g)
]
for dim_name, detail in all_details:
    fails = [d for d in detail.get("details", []) if "FAIL" in d]
    if fails:
        print(f"  ⚠️ {dim_name}: {fails[0]}")

# 存入知识库
kb.create_company_profile(
    ticker=display, name=name, market="HK", sector="互联网/电商/云计算",
    thesis="中国最大电商平台+第二大云计算服务商。AI大模型+国际化是增长引擎。分拆重组释放价值。现金流充裕，估值偏低。"
)
kb.update_company_scores(display, {
    '盈利': scores['profitability'], '健康': scores['health'],
    '现金流': scores['cashflow'], '估值': scores['valuation'],
    '成长': scores['growth'], '股东': scores['ownership'], '战略': scores['strategy'],
})
kb.update_company_financials(display, {
    '营收': f'{revenue/1e8:.0f}亿', '净利': f'{ni/1e8:.0f}亿',
    'ROE': f'{roe*100:.1f}%', '毛利率': f'{gross_margin*100:.1f}%',
    '净利率': f'{net_margin*100:.1f}%', '负债率': f'{debt_ratio*100:.1f}%',
    'PE': f'{pe:.1f}' if pe else 'N/A',
})
for risk in ["电商竞争加剧(拼多多/抖音)", "云计算增速放缓", "监管政策不确定性",
             "国际业务拓展不及预期", "分拆重组执行风险"]:
    kb.add_risk(display, risk)

# 存入DuckDB
store = YidaiStore(DB_PATH)
store.upsert_company({"ticker": display, "name": name, "market": "HK",
                      "currency": "HKD", "sector": "互联网/电商/云计算"})
for f in annual:
    f["ticker"] = display
    store.upsert_financial(f)
price["ticker"] = display
store.upsert_price(price)
store.close()

print(f"\n  ✅ 已存入知识库: knowledge/companies/{display}.md")
print(f"  ✅ 已存入DuckDB")
