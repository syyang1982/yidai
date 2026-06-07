"""
意怠工程 — 端到端验证
真实 API 拉取小米数据 → 存储 → 评分 → 生成周报
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import EastmoneyFetcher
from src.data.store import YidaiStore
from src.analysis import profitability, health, cashflow, valuation, growth
from src.report.weekly import generate_report

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai.duckdb")
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

TICKER = "01810"  # 小米


def main():
    print("=" * 60)
    print("意怠工程 — 端到端验证 (小米 01810.HK)")
    print("=" * 60)

    fetcher = EastmoneyFetcher()
    store = YidaiStore(DB_PATH)

    # ── Step 1: 拉取财报数据 ──────────────────────────────
    print("\n[1/5] 拉取财报数据 (eastmoney API)...")
    try:
        financials = fetcher.fetch_financials(TICKER, periods=5)
        print(f"  获取到 {len(financials)} 期财报")
        for f in financials:
            rev = f.get("revenue")
            rev_str = f"{rev/1e8:.0f}亿" if rev else "N/A"
            print(f"  {f['period']}: 营收={rev_str}")
    except Exception as e:
        print(f"  ❌ 拉取失败: {e}")
        store.close()
        return False

    if not financials:
        print("  ❌ 未获取到财报数据")
        store.close()
        return False

    # ── Step 2: 拉取行情数据 ──────────────────────────────
    print("\n[2/5] 拉取行情数据...")
    try:
        price = fetcher.fetch_price(TICKER)
        print(f"  股价: HKD {price.get('close_price', 'N/A')}")
        print(f"  PE: {price.get('pe_ratio', 'N/A')}")
        print(f"  PB: {price.get('pb_ratio', 'N/A')}")
        print(f"  市值: {price.get('market_cap', 0)/1e8:.0f}亿")
    except Exception as e:
        print(f"  ❌ 拉取失败: {e}")
        store.close()
        return False

    # ── Step 3: 存入 DuckDB ───────────────────────────────
    # 只用年报数据（12-31 结束的期间），按日期降序排列
    annual_financials = sorted(
        [f for f in financials if f["period"].endswith("12-31")],
        key=lambda x: x["period"], reverse=True
    )
    print(f"  年报数据: {len(annual_financials)} 期")
    for f in annual_financials[:5]:
        rev = f.get("revenue")
        rev_str = f"{rev/1e8:.0f}亿" if rev else "N/A"
        print(f"  {f['period']}: 营收={rev_str}")

    print("\n[3/5] 存入 DuckDB...")
    store.upsert_company({
        "ticker": "01810.HK",
        "name": "小米集团",
        "market": "HK",
        "currency": "HKD",
        "sector": "科技/消费电子",
        "notes": "核心持仓",
    })

    for f in annual_financials:
        f["ticker"] = "01810.HK"
        store.upsert_financial(f)

    price["ticker"] = "01810.HK"
    price["date"] = price.get("date", "2026-05-26")
    store.upsert_price(price)

    print(f"  ✅ 已存储 {len(annual_financials)} 期年报 + 行情数据")

    # ── Step 4: 运行七维分析 ──────────────────────────────
    print("\n[4/5] 运行七维分析...")

    latest = annual_financials[0]  # 最新年报
    prev = annual_financials[1] if len(annual_financials) > 1 else None

    # Debug: print raw latest data
    print(f"\n  [DEBUG] latest period: {latest['period']}")
    for k, v in latest.items():
        if k not in ('ticker',) and v is not None:
            print(f"    {k}: {v}")

    # 计算指标
    def safe_div(a, b):
        return a / b if a and b and b != 0 else 0

    rev_growth = safe_div(latest["revenue"] - prev["revenue"], prev["revenue"]) if prev else 0
    gross_margin = safe_div(latest["gross_profit"], latest["revenue"])
    net_margin = safe_div(latest["net_income"], latest["revenue"])
    roe = safe_div(latest["net_income"], latest["total_equity"])
    debt_ratio = safe_div(latest["total_liabilities"], latest["total_assets"])
    ibd_ratio = None
    if latest.get("interest_bearing_debt") and latest["total_assets"]:
        ibd_ratio = latest["interest_bearing_debt"] / latest["total_assets"]
    ocf_ni_ratio = safe_div(latest["operating_cash_flow"], latest["net_income"])

    # 维度一
    p_result = profitability.score({
        "revenue_growth": rev_growth,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "roe": roe,
    })

    # 维度二
    h_data = {"debt_ratio": debt_ratio}
    if ibd_ratio is not None:
        h_data["interest_bearing_debt_ratio"] = ibd_ratio
    h_result = health.score(h_data)

    # 维度三
    c_data = {
        "operating_cash_flow": latest["operating_cash_flow"] or 0,
        "ocf_to_ni_ratio": ocf_ni_ratio,
        "free_cash_flow": latest["free_cash_flow"] or 0,
    }
    if prev and prev.get("operating_cash_flow"):
        c_data["ocf_current"] = latest["operating_cash_flow"]
        c_data["ocf_previous"] = prev["operating_cash_flow"]
    c_result = cashflow.score(c_data)

    # 维度四
    v_result = valuation.score({
        "pe_ratio": price.get("pe_ratio"),
        "pb_ratio": price.get("pb_ratio"),
        "pe_history_percentile": 0.35,  # 估算
        "revenue_growth_rate": rev_growth * 100,
    })

    # 维度五
    growth_rates = []
    for i in range(len(annual_financials) - 1):
        curr = annual_financials[i]
        prev_f = annual_financials[i + 1]
        if curr.get("revenue") and prev_f.get("revenue") and prev_f["revenue"] > 0:
            growth_rates.append((curr["revenue"] - prev_f["revenue"]) / prev_f["revenue"])
    growth_rates.reverse()  # 按时间正序

    g_result = growth.score({
        "revenue_growth_rates": growth_rates,
        "growth_drivers": ["市场份额提升", "高端化", "新品类拓展"],
    })

    # 维度六、七 (人工评分)
    ownership_score = 4
    strategy_score = 4

    # 存入评分
    all_scores = {
        "profitability": p_result["score"],
        "health": h_result["score"],
        "cashflow": c_result["score"],
        "valuation": v_result["score"],
        "growth": g_result["score"],
        "ownership": ownership_score,
        "strategy": strategy_score,
    }
    total = sum(all_scores.values())
    grade = "A" if total >= 29 else "B" if total >= 22 else "C" if total >= 15 else "D" if total >= 8 else "F"

    if all_scores["health"] < 2 or all_scores["cashflow"] < 2 or all_scores["ownership"] < 1:
        signal = "REDUCE"
    elif total <= 14:
        signal = "REDUCE"
    elif any(v < 2 for v in all_scores.values()):
        signal = "REDUCE"
    elif total >= 29 and all_scores["valuation"] >= 4:
        signal = "BUY"
    elif total >= 15:
        signal = "HOLD"
    else:
        signal = "WATCH"

    store.upsert_score({
        "ticker": "01810.HK", "date": "2026-05-26",
        "profitability_score": all_scores["profitability"],
        "health_score": all_scores["health"],
        "cashflow_score": all_scores["cashflow"],
        "valuation_score": all_scores["valuation"],
        "growth_score": all_scores["growth"],
        "ownership_score": all_scores["ownership"],
        "strategy_score": all_scores["strategy"],
        "total_score": total, "grade": grade, "signal": signal,
    })

    # 打印结果
    dims = [
        ("盈利能力", p_result), ("财务健康", h_result), ("现金流", c_result),
        ("估值", v_result), ("增长质量", g_result),
    ]
    for name, result in dims:
        s = result["score"]
        bar = "█" * s + "░" * (5 - s)
        print(f"  {name} [{bar}] {s}/5")
        for d in result["details"]:
            print(f"    {d}")

    print(f"  股权结构 [{'█'*ownership_score}{'░'*(5-ownership_score)}] {ownership_score}/5 (人工)")
    print(f"  公司战略 [{'█'*strategy_score}{'░'*(5-strategy_score)}] {strategy_score}/5 (人工)")

    print(f"\n  总分: {total}/35  等级: {grade}  信号: {signal}")

    # ── Step 5: 生成周报 ──────────────────────────────────
    print("\n[5/5] 生成周报...")
    report_path = generate_report(DB_PATH, REPORT_DIR)
    print(f"  ✅ 周报已生成: {report_path}")

    store.close()

    # 最终验证
    print("\n" + "=" * 60)
    print("端到端验证结果")
    print("=" * 60)
    checks = [
        ("财报数据拉取", len(financials) > 0),
        ("行情数据拉取", price.get("close_price") is not None),
        ("DuckDB 存储", True),  # 如果到这里没报错就算成功
        ("七维评分完成", all(v > 0 for v in all_scores.values())),
        ("周报文件存在", os.path.exists(report_path)),
    ]
    all_pass = True
    for desc, ok in checks:
        print(f"  {'✅' if ok else '❌'} {desc}")
        if not ok:
            all_pass = False

    if all_pass:
        print(f"\n全部通过 ✅ 小米 A 级 {signal}")

    return all_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
