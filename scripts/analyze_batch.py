"""
意怠工程 — 批量分析: 安踏/顺丰/网易
数据采集 + 七维评分 + 知识库建档
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
    {"ticker": "02020", "display": "2020.HK", "name": "安踏体育", "market": "HK", "sector": "消费/运动服饰",
     "thesis": "中国运动服饰龙头，多品牌矩阵(安踏+FILA+始祖鸟)。消费升级+国潮趋势受益者。DTC转型提升利润率。",
     "risks": ["FILA增速放缓风险", "库存管理压力", "海外品牌竞争", "消费降级影响"]},
    {"ticker": "002352", "display": "002352.SZ", "name": "顺丰控股", "market": "A", "sector": "物流/快递",
     "thesis": "中国快递物流龙头，高端件市场壁垒深。鄂州花湖机场投产提升时效网络。供应链+国际业务是增长点。",
     "risks": ["快递行业价格战", "资本开支大(机场+飞机)", "利润率波动", "电商件竞争激烈"]},
    {"ticker": "09999", "display": "9999.HK", "name": "网易", "market": "HK", "sector": "互联网/游戏",
     "thesis": "中国第二大游戏公司，自研能力强(梦幻西游/阴阳师)。游戏出海+AI应用是增长引擎。现金流充裕，估值合理。",
     "risks": ["游戏版号政策", "新游戏爆款不确定性", "监管风险", "海外拓展不及预期"]},
]


def score_company(fin, prev_fin, price_data):
    """对一家公司进行七维评分。"""
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


def analyze_company(fetcher, kb, company):
    """分析单家公司。"""
    ticker = company["ticker"]
    display = company["display"]
    name = company["name"]

    print(f"\n{'='*55}")
    print(f"  {name} ({display})")
    print(f"{'='*55}")

    # 拉取数据
    all_fin = fetcher.fetch_financials(ticker, periods=10)
    annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                    key=lambda x: x["period"])
    price = fetcher.fetch_price(ticker)

    if len(annual) < 2:
        print(f"  ❌ 数据不足（仅{len(annual)}期年报）")
        return None

    latest = annual[-1]
    prev = annual[-2]

    # 评分
    scores, total, grade, sig, details = score_company(latest, prev, price)

    # 打印结果
    rev = latest.get("revenue", 0)
    ni = latest.get("net_income", 0)
    print(f"  最新年报: {latest['period']}")
    print(f"  营收: {rev/1e8:.0f}亿  净利: {ni/1e8:.0f}亿")
    print(f"  价格: {price.get('close_price', 'N/A')}  PE: {price.get('pe_ratio', 'N/A')}")

    dim_names = {"profitability": "盈利能力", "health": "财务健康", "cashflow": "现金流",
                 "valuation": "估值", "growth": "增长质量", "ownership": "股权结构", "strategy": "公司战略"}
    for dim, name_cn in dim_names.items():
        s = scores[dim]
        bar = "█" * s + "░" * (5 - s)
        print(f"  {name_cn:　<6} [{bar}] {s}/5")

    emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(sig, "❓")
    print(f"\n  总分: {total}/35  等级: {grade}  信号: {emoji} {sig}")

    # 打印关键指标
    ta = latest.get("total_assets", 0) or 0
    tl = latest.get("total_liabilities", 0) or 0
    ocf = latest.get("operating_cash_flow", 0) or 0
    print(f"  毛利率: {(latest.get('gross_profit', 0) or 0) / (rev or 1) * 100:.1f}%")
    print(f"  净利率: {(ni or 0) / (rev or 1) * 100:.1f}%")
    print(f"  ROE: {(ni or 0) / (latest.get('total_equity', 0) or 1) * 100:.1f}%")
    print(f"  负债率: {tl / (ta or 1) * 100:.1f}%")
    print(f"  经营现金流: {ocf/1e8:.0f}亿")

    # 评分详情
    detail_key_map = {"prof": "profitability", "health": "health", "cf": "cashflow", "val": "valuation", "g": "growth"}
    for dim_key, detail in details.items():
        if detail.get("details"):
            fails = [d for d in detail["details"] if "FAIL" in d]
            if fails:
                print(f"  ⚠️ {dim_names[detail_key_map.get(dim_key, dim_key)]}: {fails[0]}")

    # 存入知识库
    kb.create_company_profile(
        ticker=display, name=name, market=company["market"],
        sector=company["sector"], thesis=company["thesis"]
    )
    kb.update_company_scores(display, {
        '盈利': scores['profitability'], '健康': scores['health'],
        '现金流': scores['cashflow'], '估值': scores['valuation'],
        '成长': scores['growth'], '股东': scores['ownership'], '战略': scores['strategy'],
    })

    # 指标
    gross_margin = (latest.get("gross_profit", 0) or 0) / (rev or 1)
    net_margin = (ni or 0) / (rev or 1)
    roe = (ni or 0) / (latest.get("total_equity", 0) or 1)
    debt_ratio = tl / (ta or 1)

    kb.update_company_financials(display, {
        '营收': f'{rev/1e8:.0f}亿', '净利': f'{ni/1e8:.0f}亿',
        'ROE': f'{roe*100:.1f}%', '毛利率': f'{gross_margin*100:.1f}%',
        '净利率': f'{net_margin*100:.1f}%', '负债率': f'{debt_ratio*100:.1f}%',
        'PE': f'{price.get("pe_ratio", "N/A")}',
    })

    for risk in company["risks"]:
        kb.add_risk(display, risk)

    # 存入DuckDB
    store = YidaiStore(DB_PATH)
    store.upsert_company({"ticker": display, "name": name, "market": company["market"],
                          "currency": "HKD" if company["market"] == "HK" else "CNY",
                          "sector": company["sector"]})
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
    print("  意怠工程 — 批量分析: 安踏/顺丰/网易")
    print("=" * 55)

    fetcher = EastmoneyFetcher()
    kb = KnowledgeBase()
    results = []

    for company in COMPANIES:
        result = analyze_company(fetcher, kb, company)
        if result:
            results.append(result)

    # 汇总
    print(f"\n{'='*55}")
    print("  三家公司对比")
    print(f"{'='*55}")
    print(f"\n  {'公司':<8} {'总分':>4} {'等级':>2} {'信号':<8} {'盈利':>2} {'健康':>2} {'现金流':>2} {'估值':>2} {'增长':>2}")
    print(f"  {'-'*50}")
    for r in results:
        emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(r["signal"], "❓")
        s = r["scores"]
        print(f"  {r['name']:<8} {r['total']:>4} {r['grade']:>2} {emoji} {r['signal']:<6} "
              f"{s['profitability']:>2} {s['health']:>2} {s['cashflow']:>2} {s['valuation']:>2} {s['growth']:>2}")

    print(f"\n  知识库已更新:")
    for r in results:
        print(f"    knowledge/companies/{r['ticker']}.md")

    print(f"\n✅ 分析完成")


if __name__ == "__main__":
    main()
