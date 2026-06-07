"""
意怠工程 — 小米复盘演示
完整流程：记录决策 → 持仓跟踪 → 卖出复盘
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import EastmoneyFetcher
from src.strategy.backtest import BacktestEngine
from src.strategy.review import ReviewEngine, DecisionRecord
from src.analysis import profitability, health, cashflow, valuation, growth

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai_review.duckdb")


def score_period(fin, prev_fin=None, pe=None):
    """Score a single financial period."""
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
    from src.data.models import _compute_grade, _compute_signal
    grade = _compute_grade(total)
    sig = _compute_signal(total, *scores.values())
    return scores, total, grade, sig


def main():
    print("=" * 60)
    print("意怠工程 — 小米复盘演示")
    print("=" * 60)

    fetcher = EastmoneyFetcher()
    engine = ReviewEngine(DB_PATH)

    # ── Step 1: 获取数据 ──────────────────────────────────
    print("\n[1/4] 获取历史数据...")
    all_fin = fetcher.fetch_financials("01810", periods=20)
    annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                    key=lambda x: x["period"])
    print(f"  {len(annual)} 期年报")

    # 价格数据（简化：用回测引擎的结果）
    import requests
    prices = []
    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        for year in range(2018, 2027):
            resp = requests.get(url, params={"param": f"hk01810,month,{year}-01-01,{year}-12-31,240,qfq"},
                              headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            data = resp.json()
            klines = data.get("data", {}).get("hk01810", {}).get("month", [])
            if not klines:
                klines = data.get("data", {}).get("hk01810", {}).get("qfqmonth", [])
            for k in klines:
                if len(k) >= 2:
                    prices.append({"date": k[0], "close_price": float(k[2]) if len(k) > 2 else float(k[1])})
    except Exception:
        pass
    prices.sort(key=lambda p: p["date"])
    print(f"  {len(prices)} 个月度价格")

    # ── Step 2: 回测找交易点 ──────────────────────────────
    print("\n[2/4] 回测识别交易点...")
    bt = BacktestEngine(initial_capital=1_000_000)
    result = bt.run("01810", annual, prices)

    buy_signals = [(p, s, sc, t, g) for p, s, sc, t, g in result["signals"] if s == "BUY"]
    reduce_signals = [(p, s, sc, t, g) for p, s, sc, t, g in result["signals"] if s == "REDUCE"]

    print(f"  BUY信号: {len(buy_signals)} 次")
    print(f"  REDUCE信号: {len(reduce_signals)} 次")
    print(f"  交易: {len(result['trades'])} 笔")

    # ── Step 3: 模拟复盘流程 ──────────────────────────────
    print("\n[3/4] 复盘演示...")

    # 找第一次买入
    first_buy = next((t for t in result["trades"] if t["action"] == "BUY"), None)
    if not first_buy:
        print("  无买入交易，无法复盘")
        return

    # 找对应信号
    buy_period = None
    for period, sig, scores, total, grade in result["signals"]:
        if sig == "BUY":
            buy_period = period
            buy_scores = scores
            buy_total = total
            buy_grade = grade
            break

    # 获取该期间的财务数据
    buy_fin = next((f for f in annual if f["period"] == buy_period), None)
    buy_idx = next((i for i, f in enumerate(annual) if f["period"] == buy_period), None)
    prev_buy_fin = annual[buy_idx - 1] if buy_idx and buy_idx > 0 else None

    # 记录买入决策
    entry = DecisionRecord(
        ticker="01810.HK",
        date=first_buy["date"],
        action="BUY",
        price=first_buy["price"],
        shares=first_buy["shares"],
        value=first_buy["value"],
        profitability_score=buy_scores["profitability"],
        health_score=buy_scores["health"],
        cashflow_score=buy_scores["cashflow"],
        valuation_score=buy_scores["valuation"],
        growth_score=buy_scores["growth"],
        ownership_score=buy_scores["ownership"],
        strategy_score=buy_scores["strategy"],
        total_score=buy_total,
        grade=buy_grade,
        signal="BUY",
        revenue=buy_fin.get("revenue", 0) if buy_fin else 0,
        net_income=buy_fin.get("net_income", 0) if buy_fin else 0,
        gross_margin=(buy_fin.get("gross_profit", 0) or 0) / (buy_fin.get("revenue", 1) or 1) if buy_fin else 0,
        roe=(buy_fin.get("net_income", 0) or 0) / (buy_fin.get("total_equity", 1) or 1) if buy_fin else 0,
        debt_ratio=(buy_fin.get("total_liabilities", 0) or 0) / (buy_fin.get("total_assets", 1) or 1) if buy_fin else 0,
        thesis="营收增长强劲(+25%)，利润率提升，估值合理(PEG<1)，汽车业务带来第二增长曲线",
        risk_factors="汽车业务盈利不确定性，现金流因资本开支下降，手机行业周期性",
        confidence=4,
    )
    engine.record_decision(entry)
    print(f"\n  📝 记录买入决策:")
    print(f"     日期: {entry.date}")
    print(f"     价格: HKD {entry.price:.2f}")
    print(f"     股数: {entry.shares}")
    print(f"     评分: {buy_grade} ({buy_total}/35)")
    print(f"     理由: {entry.thesis[:50]}...")

    # 模拟持仓期间的季度快照
    print(f"\n  📊 持仓期间快照:")
    snapshot_dates = [p for p in prices if p["date"] > first_buy["date"]][:6]
    for snap_price in snapshot_dates:
        # 用买入时的评分模拟（实际中应该用最新数据重新评分）
        snap = engine.take_snapshot(
            "01810.HK",
            snap_price["close_price"],
            buy_scores,  # 简化：用相同评分
            entry,
        )
        chg = snap.price_change_pct
        emoji = "📈" if chg > 0 else "📉" if chg < 0 else "➡️"
        print(f"     {snap.date}: {emoji} HKD {snap_price['close_price']:.2f} ({chg:+.1f}%) 评分变化:{snap.score_delta:+d}")

    # 找卖出交易
    first_sell = next((t for t in result["trades"] if t["action"] == "SELL"), None)
    if first_sell:
        # 找卖出时的评分
        sell_period = None
        for period, sig, scores, total, grade in result["signals"]:
            if sig == "REDUCE":
                sell_period = period
                sell_scores = scores
                sell_total = total
                break

        sell_fin = next((f for f in annual if f["period"] == sell_period), None)
        sell_idx = next((i for i, f in enumerate(annual) if f["period"] == sell_period), None)
        prev_sell_fin = annual[sell_idx - 1] if sell_idx and sell_idx > 0 else None

        # 生成复盘
        review = engine.generate_review(
            "01810.HK",
            first_sell["date"],
            first_sell["price"],
            sell_scores,
        )

        print(f"\n  📋 复盘报告:")
        print(f"     持仓天数: {review.holding_days} 天")
        print(f"     买入价:   HKD {review.entry_price:.2f}")
        print(f"     卖出价:   HKD {review.exit_price:.2f}")
        print(f"     收益率:   {review.return_pct:.1f}%")
        print(f"     盈亏:     {review.pnl/1e4:.1f}万")
        print(f"     评分轨迹: {review.score_trajectory}")
        print(f"\n     ✅ 做对了: {review.what_was_right}")
        print(f"     ❌ 做错了: {review.what_was_wrong}")
        if review.missed_signals:
            print(f"     ⚠️ 忽略的信号: {review.missed_signals}")
        print(f"     📚 教训: {review.lessons}")

        # 记录第二次买入（如果有）
        second_buy = next((t for t in result["trades"] if t["action"] == "BUY" and t["date"] > first_sell["date"]), None)
        if second_buy:
            buy2_period = None
            for period, sig, scores, total, grade in result["signals"]:
                if sig == "BUY" and period > sell_period:
                    buy2_period = period
                    buy2_scores = scores
                    buy2_total = total
                    buy2_grade = grade
                    break
            else:
                buy2_period = None

            if buy2_period:
                buy2_fin = next((f for f in annual if f["period"] == buy2_period), None)
                entry2 = DecisionRecord(
                    ticker="01810.HK",
                    date=second_buy["date"],
                    action="BUY",
                    price=second_buy["price"],
                    shares=second_buy["shares"],
                    value=second_buy["value"],
                    profitability_score=buy2_scores["profitability"],
                    health_score=buy2_scores["health"],
                    cashflow_score=buy2_scores["cashflow"],
                    valuation_score=buy2_scores["valuation"],
                    growth_score=buy2_scores["growth"],
                    ownership_score=buy2_scores["ownership"],
                    strategy_score=buy2_scores["strategy"],
                    total_score=buy2_total,
                    grade=buy2_grade,
                    signal="BUY",
                    revenue=buy2_fin.get("revenue", 0) if buy2_fin else 0,
                    thesis="上一次教训：卖出太早。这次基于更强的基本面信号重新买入，营收+34%，利润率创新高",
                    risk_factors="估值比第一次高(PE 19 vs 16)，需要更严格止损",
                    confidence=3,
                )
                engine.record_decision(entry2)
                print(f"\n  📝 记录第二次买入决策:")
                print(f"     日期: {entry2.date}")
                print(f"     价格: HKD {entry2.price:.2f}")
                print(f"     评分: {buy2_grade} ({buy2_total}/35)")
                print(f"     反思: {entry2.thesis[:60]}...")

    # ── Step 4: 汇总 ─────────────────────────────────────
    print("\n[4/4] 复盘系统状态:")
    decisions = engine.get_decision_history("01810.HK")
    snapshots = engine.get_holding_snapshots("01810.HK")
    reviews = engine.get_reviews("01810.HK")
    print(f"  决策记录: {len(decisions)} 条")
    print(f"  持仓快照: {len(snapshots)} 条")
    print(f"  复盘报告: {len(reviews)} 份")

    print("\n✅ 复盘演示完成")


if __name__ == "__main__":
    main()
