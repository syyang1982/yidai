"""分析B站 (9626.HK) 和 乐信 (LX)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import EastmoneyFetcher
from src.data.store import YidaiStore
from src.analysis import profitability, health, cashflow, valuation, growth
from src.data.models import _compute_grade, _compute_signal
from src.knowledge.base import KnowledgeBase

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai.duckdb")

COMPANIES = [
    {"ticker": "09626", "display": "9626.HK", "name": "B站",
     "market": "HK", "sector": "互联网/视频/游戏",
     "thesis": "中国最大年轻人视频社区，MAU 3亿+。广告+游戏+直播变现空间大。首次盈利证明商业模式可行。",
     "risks": ["用户增长放缓", "内容成本高", "游戏自研能力待验证", "短视频竞争(抖音/快手)"]},
    {"ticker": "LX", "display": "LX", "name": "乐信",
     "market": "US", "sector": "金融科技/消费信贷",
     "thesis": "中国领先消费金融科技平台，连接银行资金和年轻消费者。AI风控能力强，资产质量改善。低估值+高分红。",
     "risks": ["信贷周期风险", "监管政策变化", "资产质量恶化", "宏观经济下行"]},
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
        # Try listing available periods
        if all_fin:
            print(f"  可用期间: {[f['period'] for f in all_fin[:5]]}")
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
    if pe:
        print(f"  价格: {price.get('close_price', 'N/A')}  PE: {pe:.1f}")
    else:
        print(f"  价格: {price.get('close_price', 'N/A')}  PE: N/A")

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
                          "currency": "HKD" if company["market"] == "HK" else "USD",
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
    print("  意怠工程 — B站 + 乐信")
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
    print("  对比")
    print(f"{'='*55}")
    for r in results:
        emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(r["signal"], "❓")
        s = r["scores"]
        print(f"  {r['name']:<8} {r['total']:>4} {r['grade']:>2} {emoji} {r['signal']:<6} "
              f"P={s['profitability']} H={s['health']} C={s['cashflow']} V={s['valuation']} G={s['growth']}")

    print(f"\n✅ 分析完成")


if __name__ == "__main__":
    main()
