"""
意怠工程 — 小米真实持仓复盘
基于 Frank 的实际买入和持有，而非回测模拟
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from src.data.fetcher import EastmoneyFetcher
from src.strategy.review import ReviewEngine, DecisionRecord
from src.analysis import profitability, health, cashflow, valuation, growth
from src.data.models import _compute_grade, _compute_signal

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai_review.duckdb")


def score_period(fin, prev_fin=None, pe=None):
    """对单期财报评分。"""
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
    h = health.score({"debt_ratio": tl / ta if ta > 0 else 0})

    ocf = fin.get("operating_cash_flow", 0) or 0
    ni = fin.get("net_income", 0) or 1
    cf = cashflow.score({
        "operating_cash_flow": ocf,
        "ocf_to_ni_ratio": ocf / ni if ni else 0,
        "free_cash_flow": fin.get("free_cash_flow", 0) or 0,
    })

    v = valuation.score({
        "pe_ratio": pe,
        "pe_history_percentile": None,
        "revenue_growth_rate": rev_growth * 100,
    })

    g = growth.score({
        "revenue_growth_rates": [rev_growth] if rev_growth else [],
        "growth_drivers": ["市场份额提升", "高端化", "新品类拓展"],
    })

    scores = {
        "profitability": prof["score"], "health": h["score"],
        "cashflow": cf["score"], "valuation": v["score"],
        "growth": g["score"], "ownership": 4, "strategy": 4,
    }
    total = sum(scores.values())
    grade = _compute_grade(total)
    sig = _compute_signal(total, *scores.values())
    return scores, total, grade, sig, {
        "prof": prof["details"], "health": h["details"],
        "cf": cf["details"], "val": v["details"], "g": g["details"],
    }


def main():
    print("=" * 60)
    print("意怠工程 — 小米 (01810.HK) 真实持仓复盘")
    print("=" * 60)

    fetcher = EastmoneyFetcher()
    engine = ReviewEngine(DB_PATH)

    # ── 获取数据 ──────────────────────────────────────────
    print("\n[1/3] 获取历史数据...")
    all_fin = fetcher.fetch_financials("01810", periods=20)
    annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                    key=lambda x: x["period"])
    print(f"  {len(annual)} 期年报")

    # 获取当前价格
    price_data = fetcher.fetch_price("01810")
    current_price = price_data.get("close_price", 0)
    current_pe = price_data.get("pe_ratio", 0)
    print(f"  当前价格: HKD {current_price:.2f}")
    print(f"  当前PE: {current_pe:.1f}")

    # ── 逐年评分 ──────────────────────────────────────────
    print("\n[2/3] 历年七维评分（观察持仓期间公司质量变化）...")
    print()

    # 你持有小米期间（假设2021年左右开始持有）
    # 这里展示所有年报的评分
    score_history = []
    pe_history = []

    for i, fin in enumerate(annual):
        prev = annual[i-1] if i > 0 else None
        # 简化PE：用当前PE的估算
        # 实际中应该用每个报告期的市场价格
        period_pe = current_pe if fin["period"] >= "2024-12-31" else None

        scores, total, grade, sig, details = score_period(fin, prev, period_pe)
        score_history.append({
            "period": fin["period"],
            "scores": scores,
            "total": total,
            "grade": grade,
            "signal": sig,
            "revenue": fin.get("revenue", 0),
            "net_income": fin.get("net_income", 0),
        })

        bar = "█" * (total // 5) + "░" * (7 - total // 5)
        emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(sig, "❓")
        rev_str = f"{fin.get('revenue', 0)/1e8:.0f}亿" if fin.get("revenue") else "N/A"
        ni_str = f"{fin.get('net_income', 0)/1e8:.0f}亿" if fin.get("net_income") else "N/A"

        print(f"  {fin['period']}: {emoji} {sig:6} {grade} ({total:2d}/35) "
              f"营收={rev_str:>5} 净利={ni_str:>4} "
              f"P={scores['profitability']} H={scores['health']} "
              f"C={scores['cashflow']} V={scores['valuation']} "
              f"G={scores['growth']}")

    # ── 记录真实持仓 ──────────────────────────────────────
    print("\n[3/3] 记录当前持仓状态...")

    latest = score_history[-1]
    latest_fin = annual[-1]
    prev_fin = annual[-2] if len(annual) > 1 else None

    # 记录当前持仓（这不是买入决策，而是当前状态快照）
    current_record = DecisionRecord(
        ticker="01810.HK",
        date=datetime.now().strftime("%Y-%m-%d"),
        action="HOLD",  # 当前状态：持有
        price=current_price,
        shares=34000,   # 约34K股
        value=current_price * 34000,
        profitability_score=latest["scores"]["profitability"],
        health_score=latest["scores"]["health"],
        cashflow_score=latest["scores"]["cashflow"],
        valuation_score=latest["scores"]["valuation"],
        growth_score=latest["scores"]["growth"],
        ownership_score=latest["scores"]["ownership"],
        strategy_score=latest["scores"]["strategy"],
        total_score=latest["total"],
        grade=latest["grade"],
        signal=latest["signal"],
        revenue=latest_fin.get("revenue", 0),
        net_income=latest_fin.get("net_income", 0),
        gross_margin=(latest_fin.get("gross_profit", 0) or 0) / (latest_fin.get("revenue", 1) or 1),
        roe=(latest_fin.get("net_income", 0) or 0) / (latest_fin.get("total_equity", 1) or 1),
        debt_ratio=(latest_fin.get("total_liabilities", 0) or 0) / (latest_fin.get("total_assets", 1) or 1),
        thesis="核心持仓，长期看好AI+汽车+IoT生态。短期波动不影响长期判断。",
        risk_factors="汽车业务盈利拐点未到，现金流因资本开支承压，地缘政治风险",
        confidence=4,
    )
    engine.record_decision(current_record)

    print(f"\n  当前持仓状态:")
    print(f"  ├─ 持仓: ~34,000 股")
    print(f"  ├─ 价格: HKD {current_price:.2f}")
    print(f"  ├─ 市值: ~{current_price * 34000 / 1e4:.0f}万 HKD")
    print(f"  ├─ 评分: {latest['grade']} ({latest['total']}/35)")
    print(f"  └─ 信号: {latest['signal']}")

    # 趋势分析
    print(f"\n  持仓期间公司质量变化:")
    if len(score_history) >= 3:
        recent = score_history[-3:]
        for i in range(1, len(recent)):
            delta = recent[i]["total"] - recent[i-1]["total"]
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            print(f"    {recent[i-1]['period']} → {recent[i]['period']}: "
                  f"{recent[i-1]['total']} → {recent[i]['total']} ({arrow}{abs(delta)})")

    # 关键维度变化
    print(f"\n  关键维度趋势 (vs 上一年):")
    if len(score_history) >= 2:
        dim_names = {
            "profitability": "盈利能力", "health": "财务健康",
            "cashflow": "现金流", "valuation": "估值",
            "growth": "增长质量", "ownership": "股权结构", "strategy": "公司战略",
        }
        curr = score_history[-1]["scores"]
        prev = score_history[-2]["scores"]
        for dim, name in dim_names.items():
            c = curr[dim]
            p = prev[dim]
            delta = c - p
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            bar = "█" * c + "░" * (5 - c)
            print(f"    {name:　<6} [{bar}] {c}/5 ({arrow}{abs(delta)})")

    print(f"\n  策略建议:")
    sig = latest["signal"]
    if sig == "BUY":
        print(f"    🟢 当前评分A级，估值合理，可考虑加仓")
    elif sig == "HOLD":
        print(f"    🟡 当前评分良好，继续持有观察")
    elif sig == "REDUCE":
        print(f"    🔴 有维度亮红灯，需要关注风险")
    else:
        print(f"    🔵 观望中")

    print(f"\n✅ 真实持仓复盘完成")
    print(f"\n下一步: 每次财报发布后运行此脚本，记录快照，跟踪变化趋势")


if __name__ == "__main__":
    main()
