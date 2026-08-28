"""
意怠工程 — 批量分析5家公司:
金山云 金山软件 名创优品 蜜雪集团 微创机器人
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import EastmoneyFetcher
from src.data.store import YidaiStore
from src.analysis import profitability, health, cashflow, valuation, growth
from src.data.models import _compute_grade, _compute_signal
from src.knowledge.base import KnowledgeBase

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai.duckdb")

COMPANIES = [
    {"ticker": "03896", "display": "3896.HK", "name": "金山云",
     "market": "HK", "sector": "云计算/SaaS",
     "thesis": "金山系云计算平台，受益于AI算力需求爆发。与金山办公协同，政企客户基础扎实。",
     "risks": ["云计算行业竞争激烈(阿里云/华为云)", "盈利能力待验证", "客户集中度高"]},
    {"ticker": "03888", "display": "3888.HK", "name": "金山软件",
     "market": "HK", "sector": "软件/办公",
     "thesis": "金山办公(WPS)母公司，国产办公软件龙头。信创+AI办公双轮驱动。游戏业务提供现金流。",
     "risks": ["WPS付费转化率", "游戏业务波动", "AI投入产出比"]},
    {"ticker": "09896", "display": "9896.HK", "name": "名创优品",
     "market": "HK", "sector": "零售/消费",
     "thesis": "全球化生活好物集合店，海外扩张迅速。IP联名策略提升品牌力。高毛利+轻资产模式。",
     "risks": ["海外扩张执行风险", "消费降级影响", "IP联名依赖", "库存管理"]},
    {"ticker": "02097", "display": "2097.HK", "name": "蜜雪集团",
     "market": "HK", "sector": "餐饮/茶饮",
     "thesis": "中国最大茶饮连锁(蜜雪冰城)，4万+门店。极致性价比+供应链优势。下沉市场王者。",
     "risks": ["加盟商管理风险", "食品安全事件", "增长天花板", "海外市场不确定性"]},
    {"ticker": "02252", "display": "2252.HK", "name": "微创机器人",
     "market": "HK", "sector": "医疗器械/手术机器人",
     "thesis": "国产手术机器人龙头，替代进口达芬奇。多产品线布局(骨科/腔镜/血管介入)。高成长赛道。",
     "risks": ["商业化早期亏损", "研发投入大", "集采压价风险", "达芬奇竞争"]},
]


def score_company(fin, prev_fin, price_data):
    revenue = fin.get("revenue", 0) or 0
    denom = revenue if revenue else 1
    rev_growth = 0
    if prev_fin:
        prev_rev = prev_fin.get("revenue", 0) or 0
        if prev_rev > 0:
            rev_growth = (revenue - prev_rev) / prev_rev

    ta = fin.get("total_assets", 0) or 0
    tl = fin.get("total_liabilities", 0) or 0

    prof = profitability.score({
        "revenue_growth": rev_growth,
        "gross_margin": (fin.get("gross_profit", 0) or 0) / denom,
        "net_margin": (fin.get("net_income", 0) or 0) / denom,
        "roe": (fin.get("net_income", 0) or 0) / (fin.get("total_equity", 0) or 1),
    })
    h_data = {"debt_ratio": tl / ta if ta > 0 else 0}
    ibd = fin.get("interest_bearing_debt")
    if ibd and ta > 0:
        h_data["interest_bearing_debt_ratio"] = ibd / ta
    h = health.score(h_data)

    ocf = fin.get("operating_cash_flow", 0) or 0
    ni = fin.get("net_income", 0) or 1
    fcf = fin.get("free_cash_flow")
    cf = cashflow.score({
        "operating_cash_flow": ocf,
        "ocf_to_ni_ratio": ocf / ni if ni else 0,
        "free_cash_flow": fcf if fcf else 0,
    })

    pe = price_data.get("pe_ratio")
    v = valuation.score({
        "pe_ratio": pe,
        "pe_history_percentile": None,
        "revenue_growth_rate": rev_growth * 100,
    })

    g = growth.score({
        "revenue_growth_rates": [rev_growth] if rev_growth else [],
        "growth_drivers": ["市场份额提升", "行业增长"],
    })

    scores = {
        "profitability": prof["score"], "health": h["score"],
        "cashflow": cf["score"], "valuation": v["score"],
        "growth": g["score"], "ownership": 4, "strategy": 4,
    }
    total = sum(scores.values())
    grade = _compute_grade(total)
    sig = _compute_signal(total, *scores.values())
    details = {"prof": prof, "health": h, "cf": cf, "val": v, "g": g}
    return scores, total, grade, sig, details


def analyze(fetcher, kb, company):
    ticker = company["ticker"]
    display = company["display"]
    name = company["name"]

    print(f"\n{'='*55}")
    print(f"  {name} ({display})")
    print(f"{'='*55}")

    all_fin = fetcher.fetch_financials(ticker, periods=10)
    annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                    key=lambda x: x["period"])
    price = fetcher.fetch_price(ticker)

    if len(annual) < 2:
        print(f"  ❌ 数据不足（{len(annual)}期）")
        return None

    latest = annual[-1]
    prev = annual[-2]

    scores, total, grade, sig, details = score_company(latest, prev, price)

    rev = latest.get("revenue", 0) or 0
    ni = latest.get("net_income", 0) or 0
    ta = latest.get("total_assets", 0) or 0
    tl = latest.get("total_liabilities", 0) or 0
    ocf = latest.get("operating_cash_flow", 0) or 0
    pe = price.get("pe_ratio")

    print(f"  年报: {latest['period']}")
    print(f"  营收: {rev/1e8:.0f}亿  净利: {ni/1e8:.0f}亿  经营现金流: {ocf/1e8:.0f}亿")
    print(f"  价格: {price.get('close_price', 'N/A')}  PE: {pe:.1f}" if pe else f"  价格: N/A")

    dim_cn = {"profitability": "盈利能力", "health": "财务健康", "cashflow": "现金流",
              "valuation": "估值", "growth": "增长质量", "ownership": "股权结构", "strategy": "公司战略"}
    for dim, cn in dim_cn.items():
        s = scores[dim]
        bar = "█" * s + "░" * (5 - s)
        print(f"  {cn:　<6} [{bar}] {s}/5")

    emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(sig, "❓")
    print(f"\n  总分: {total}/35  等级: {grade}  信号: {emoji} {sig}")

    gross_margin = (latest.get("gross_profit", 0) or 0) / (rev or 1)
    net_margin = (ni or 0) / (rev or 1)
    roe = (ni or 0) / (latest.get("total_equity", 0) or 1)
    debt_ratio = tl / (ta or 1)
    print(f"  毛利率: {gross_margin*100:.1f}%  净利率: {net_margin*100:.1f}%  ROE: {roe*100:.1f}%  负债率: {debt_ratio*100:.1f}%")

    detail_map = {"prof": "盈利能力", "health": "财务健康", "cf": "现金流", "val": "估值", "g": "增长"}
    for k, d in details.items():
        fails = [x for x in d.get("details", []) if "FAIL" in x]
        if fails:
            print(f"  ⚠️ {detail_map[k]}: {fails[0]}")

    # 知识库
    kb.create_company_profile(ticker=display, name=name, market=company["market"],
                              sector=company["sector"], thesis=company["thesis"])
    kb.update_company_scores(display, {
        '盈利': scores['profitability'], '健康': scores['health'],
        '现金流': scores['cashflow'], '估值': scores['valuation'],
        '成长': scores['growth'], '股东': scores['ownership'], '战略': scores['strategy'],
    })
    kb.update_company_financials(display, {
        '营收': f'{rev/1e8:.0f}亿', '净利': f'{ni/1e8:.0f}亿',
        'ROE': f'{roe*100:.1f}%', '毛利率': f'{gross_margin*100:.1f}%',
        '净利率': f'{net_margin*100:.1f}%', '负债率': f'{debt_ratio*100:.1f}%',
        'PE': f'{pe:.1f}' if pe else 'N/A',
    })
    for r in company["risks"]:
        kb.add_risk(display, r)

    # DuckDB
    store = YidaiStore(DB_PATH)
    store.upsert_company({"ticker": display, "name": name, "market": company["market"],
                          "currency": "HKD", "sector": company["sector"]})
    for f in annual:
        f["ticker"] = display
        store.upsert_financial(f)
    price["ticker"] = display
    store.upsert_price(price)
    store.close()

    return {"ticker": display, "name": name, "scores": scores, "total": total,
            "grade": grade, "signal": sig}


def main():
    print("=" * 55)
    print("  意怠工程 — 批量分析5家公司")
    print("=" * 55)

    fetcher = EastmoneyFetcher()
    kb = KnowledgeBase()
    results = []

    for c in COMPANIES:
        r = analyze(fetcher, kb, c)
        if r:
            results.append(r)

    # 汇总
    print(f"\n{'='*55}")
    print("  五家公司对比")
    print(f"{'='*55}")
    print(f"\n  {'公司':<8} {'总分':>4} {'等级':>2} {'信号':<8} {'盈利':>2} {'健康':>2} {'现金流':>2} {'估值':>2} {'增长':>2}")
    print(f"  {'-'*50}")
    for r in sorted(results, key=lambda x: x["total"], reverse=True):
        emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(r["signal"], "❓")
        s = r["scores"]
        print(f"  {r['name']:<8} {r['total']:>4} {r['grade']:>2} {emoji} {r['signal']:<6} "
              f"{s['profitability']:>2} {s['health']:>2} {s['cashflow']:>2} {s['valuation']:>2} {s['growth']:>2}")

    print(f"\n  知识库: {[r['ticker'] for r in results]}")
    print(f"\n✅ 分析完成")


if __name__ == "__main__":
    main()
