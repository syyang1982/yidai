"""
意怠工程 — 策略对比：v1(年度+全仓) vs v2(季报+趋势+分批)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import EastmoneyFetcher
from src.strategy.backtest import BacktestEngine
from src.strategy.backtest_v2 import BacktestEngineV2
import requests


def get_data():
    """获取小米历史数据。"""
    fetcher = EastmoneyFetcher()

    # 财报（所有期间，含季报）
    all_fin = fetcher.fetch_financials("01810", periods=50)
    annual = sorted([f for f in all_fin if f["period"].endswith("12-31")],
                    key=lambda x: x["period"])
    # 所有期间（含季报）
    all_periods = sorted(all_fin, key=lambda x: x["period"])

    # 价格
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

    return annual, all_periods, prices


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_signals(signals, label):
    print(f"\n  {label} 信号:")
    for item in signals:
        period = item[0]
        signal = item[1]
        scores = item[2]
        total = item[3]
        grade = item[4]
        trend = item[5] if len(item) > 5 else "N/A"
        emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(signal, "❓")
        partial = " [趋势过滤]" if trend == "below_ma" else ""
        print(f"    {period}: {emoji} {signal:6} {grade} ({total:2d}/35) {trend}{partial}")


def print_trades(trades, label):
    print(f"\n  {label} 交易:")
    if not trades:
        print("    无交易")
        return
    for t in trades:
        emoji = "🟢" if t["action"] == "BUY" else "🔴"
        partial = " [分批]" if t.get("partial") else ""
        print(f"    {emoji} {t['date']} {t['action']:4} {t['shares']:>6}股 "
              f"@ HKD {t['price']:>6.2f} (总值: {t['value']/1e4:>6.1f}万){partial}")


def print_metrics(m, label):
    print(f"\n  {label} 指标:")
    print(f"    总收益:     {m['total_return']*100:>6.1f}%")
    print(f"    年化收益:   {m['cagr']*100:>6.1f}%")
    print(f"    最大回撤:   {m['max_drawdown']*100:>6.1f}%")
    print(f"    夏普比率:   {m['sharpe_ratio']:>6.2f}")
    print(f"    基准收益:   {m['benchmark_return']*100:>6.1f}%")
    print(f"    超额收益:   {m['alpha']*100:>6.1f}%")
    print(f"    交易次数:   {m['num_trades']}")
    if 'trend_filter_blocked' in m:
        print(f"    趋势过滤:   {m['trend_filter_blocked']} 次BUY被阻止")


def main():
    print("=" * 60)
    print("  意怠工程 — 策略对比: v1 vs v2")
    print("  小米 (01810.HK)")
    print("=" * 60)

    annual, all_periods, prices = get_data()
    print(f"\n  数据: {len(annual)} 期年报, {len(all_periods)} 期总报告, {len(prices)} 个月度价格")

    # ── v1: 年度 + 全仓 ──────────────────────────────────
    print_header("v1 策略: 年度信号 + 全仓进出")
    v1 = BacktestEngine(initial_capital=1_000_000)
    r1 = v1.run("01810", annual, prices)
    print_signals(r1["signals"], "v1")
    print_trades(r1["trades"], "v1")
    if r1["portfolio_values"]:
        print(f"\n  v1 最终市值: {r1['portfolio_values'][-1][1]/1e4:.1f}万")
    print_metrics(r1["metrics"], "v1")

    # ── v2: 季报 + 趋势 + 分批 ──────────────────────────
    print_header("v2 策略: 季报信号 + 趋势过滤 + 分批建仓")
    v2 = BacktestEngineV2(initial_capital=1_000_000, config={
        "use_quarterly": True,
        "trend_filter_enabled": True,
        "ma_period": 200,
        "max_drawdown_stop": 0.30,
        "position_sizing": "gradual",
        "buy_pct": 0.50,
        "add_pct": 0.25,
        "reduce_pct": 0.50,
        "yoy_growth": True,
    })
    r2 = v2.run("01810", all_periods, prices)
    print_signals(r2["signals"], "v2")
    print_trades(r2["trades"], "v2")
    if r2["portfolio_values"]:
        print(f"\n  v2 最终市值: {r2['portfolio_values'][-1][1]/1e4:.1f}万")
    print_metrics(r2["metrics"], "v2")

    # ── v2 无趋势过滤（对比） ────────────────────────────
    print_header("v2b 策略: 季报+分批 但无趋势过滤")
    v2b = BacktestEngineV2(initial_capital=1_000_000, config={
        "use_quarterly": True,
        "trend_filter_enabled": False,
        "position_sizing": "gradual",
        "buy_pct": 0.50,
        "reduce_pct": 0.50,
        "yoy_growth": True,
    })
    r2b = v2b.run("01810", all_periods, prices)
    if r2b["portfolio_values"]:
        print(f"\n  v2b 最终市值: {r2b['portfolio_values'][-1][1]/1e4:.1f}万")
    print_metrics(r2b["metrics"], "v2b")

    # ── 对比总结 ─────────────────────────────────────────
    print_header("策略对比总结")

    v1_final = r1["portfolio_values"][-1][1] if r1["portfolio_values"] else 0
    v2_final = r2["portfolio_values"][-1][1] if r2["portfolio_values"] else 0
    v2b_final = r2b["portfolio_values"][-1][1] if r2b["portfolio_values"] else 0
    bm_final = r1["benchmark_values"][-1][1] if r1["benchmark_values"] else 0

    print(f"\n  {'策略':<20} {'最终市值':>10} {'总收益':>8} {'年化':>8} {'回撤':>8} {'交易':>4}")
    print(f"  {'-'*62}")
    print(f"  {'v1 年度+全仓':<18} {v1_final/1e4:>8.1f}万 {r1['metrics']['total_return']*100:>7.1f}% {r1['metrics']['cagr']*100:>7.1f}% {r1['metrics']['max_drawdown']*100:>7.1f}% {r1['metrics']['num_trades']:>4}")
    print(f"  {'v2 季报+趋势+分批':<18} {v2_final/1e4:>8.1f}万 {r2['metrics']['total_return']*100:>7.1f}% {r2['metrics']['cagr']*100:>7.1f}% {r2['metrics']['max_drawdown']*100:>7.1f}% {r2['metrics']['num_trades']:>4}")
    print(f"  {'v2b 季报+分批':<18} {v2b_final/1e4:>8.1f}万 {r2b['metrics']['total_return']*100:>7.1f}% {r2b['metrics']['cagr']*100:>7.1f}% {r2b['metrics']['max_drawdown']*100:>7.1f}% {r2b['metrics']['num_trades']:>4}")
    print(f"  {'买入持有':<18} {bm_final/1e4:>8.1f}万 {r1['metrics']['benchmark_return']*100:>7.1f}%")

    print(f"\n  结论:")
    if v2_final > v1_final:
        print(f"  ✅ v2 表现优于 v1 (+{(v2_final-v1_final)/1e4:.1f}万)")
    elif v2_final < v1_final:
        print(f"  ❌ v2 表现不如 v1 ({(v2_final-v1_final)/1e4:.1f}万)")
    else:
        print(f"  ➡️ v1 和 v2 表现相同")

    if r2["metrics"]["max_drawdown"] < r1["metrics"]["max_drawdown"]:
        print(f"  ✅ v2 回撤更小 ({r2['metrics']['max_drawdown']*100:.1f}% vs {r1['metrics']['max_drawdown']*100:.1f}%)")

    if r2["metrics"].get("trend_filter_blocked", 0) > 0:
        print(f"  📊 趋势过滤阻止了 {r2['metrics']['trend_filter_blocked']} 次BUY信号")

    print(f"\n  ✅ 对比完成")


if __name__ == "__main__":
    main()
