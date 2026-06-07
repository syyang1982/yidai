"""
意怠工程 — 小米 (1810.HK) 历史回测
用真实财报数据 + 历史价格，验证七维评分策略的历史表现
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import EastmoneyFetcher
from src.strategy.backtest import BacktestEngine

TICKER = "01810"


def main():
    print("=" * 60)
    print("意怠工程 — 小米 (01810.HK) 历史回测")
    print("=" * 60)

    fetcher = EastmoneyFetcher()

    # ── Step 1: 拉取年报数据 ──────────────────────────────
    print("\n[1/3] 拉取年报数据...")
    all_financials = fetcher.fetch_financials(TICKER, periods=20)
    # 只保留年报 (12-31)
    annual_financials = sorted(
        [f for f in all_financials if f["period"].endswith("12-31")],
        key=lambda x: x["period"]
    )
    print(f"  获取到 {len(annual_financials)} 期年报")
    for f in annual_financials:
        rev = f.get("revenue")
        print(f"  {f['period']}: 营收={rev/1e8:.0f}亿" if rev else f"  {f['period']}: N/A")

    # ── Step 2: 拉取历史价格 ──────────────────────────────
    print("\n[2/3] 拉取历史价格...")
    # 小米2018年7月上市，用腾讯API拉取历史K线
    import requests
    price_history = []
    try:
        # 用腾讯API拉取港股历史数据
        start_year = 2018
        end_year = 2026
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        for year in range(start_year, end_year + 1):
            params = {
                "param": f"hk01810,month,{year}-01-01,{year}-12-31,240,qfq"
            }
            try:
                resp = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                data = resp.json()
                klines = data.get("data", {}).get("hk01810", {}).get("month", [])
                if not klines:
                    klines = data.get("data", {}).get("hk01810", {}).get("qfqmonth", [])
                for k in klines:
                    if len(k) >= 2:
                        # [date, open, close, high, low, volume]
                        price_history.append({
                            "date": k[0],
                            "close_price": float(k[2]) if len(k) > 2 else float(k[1]),
                        })
            except Exception:
                continue
    except Exception as e:
        print(f"  ⚠️ 历史价格拉取失败: {e}")

    if not price_history:
        print("  ❌ 无历史价格数据，无法回测")
        return False

    price_history.sort(key=lambda p: p["date"])
    print(f"  获取到 {len(price_history)} 个月度价格")
    print(f"  时间范围: {price_history[0]['date']} ~ {price_history[-1]['date']}")
    print(f"  起始价: HKD {price_history[0]['close_price']:.2f}")
    print(f"  最新价: HKD {price_history[-1]['close_price']:.2f}")

    # ── Step 3: 运行回测 ──────────────────────────────────
    print("\n[3/3] 运行回测...")
    engine = BacktestEngine(initial_capital=1_000_000)
    result = engine.run(
        ticker=TICKER,
        annual_financials=annual_financials,
        price_history=price_history,
        ownership_scores={},   # 全用默认值4
        strategy_scores={},    # 全用默认值4
    )

    # 打印信号
    print("\n" + "=" * 60)
    print("历年信号")
    print("=" * 60)
    for period, signal, scores, total, grade in result["signals"]:
        dim_str = " | ".join(f"{k}:{v}" for k, v in scores.items())
        emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(signal, "❓")
        print(f"  {period}: {emoji} {signal:6} {grade} ({total}/35) [{dim_str}]")

    # 打印交易
    print("\n" + "=" * 60)
    print("交易记录")
    print("=" * 60)
    if result["trades"]:
        for t in result["trades"]:
            emoji = "🟢" if t["action"] == "BUY" else "🔴"
            print(f"  {emoji} {t['date']} {t['action']} {t['shares']}股 @ HKD {t['price']:.2f} (总值: {t['value']/1e4:.1f}万)")
    else:
        print("  无交易")

    # 打印指标
    m = result["metrics"]
    print("\n" + "=" * 60)
    print("回测指标")
    print("=" * 60)
    print(f"  初始资金:     100万")
    if result["portfolio_values"]:
        final_val = result["portfolio_values"][-1][1]
        print(f"  最终市值:     {final_val/1e4:.1f}万")
    print(f"  策略总收益:   {m['total_return']*100:.1f}%")
    print(f"  策略年化收益: {m['cagr']*100:.1f}%")
    print(f"  最大回撤:     {m['max_drawdown']*100:.1f}%")
    print(f"  夏普比率:     {m['sharpe_ratio']:.2f}")
    print(f"  基准总收益:   {m['benchmark_return']*100:.1f}%")
    print(f"  超额收益:     {m['alpha']*100:.1f}%")
    print(f"  交易次数:     {m['num_trades']}")
    print(f"  胜率:         {m['win_rate']*100:.0f}%" if m['win_rate'] is not None else "  胜率:         N/A")

    print("\n✅ 回测完成")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
