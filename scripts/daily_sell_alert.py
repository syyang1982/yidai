#!/usr/bin/env python3
"""每日卖出提醒扫描脚本 — 供 cron job 调用。

逻辑:
1. 刷新持仓价格 (portfolio_status.py refresh)
2. 运行卖出提醒扫描
3. 仅当有 CRITICAL 或 WARNING 级别提醒时输出 (触发推送)
4. 无提醒时静默 (不推送)
"""

import sys
import os

# 确保 yidai 模块可导入
YIDAI_ROOT = os.path.expanduser("~/.hermes/yidai")
sys.path.insert(0, YIDAI_ROOT)
os.chdir(YIDAI_ROOT)

def main():
    # Step 1: 刷新价格 (静默, 失败不阻断)
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.expanduser("~/.hermes/scripts/portfolio_status.py"), "refresh"],
            capture_output=True, timeout=120, cwd=os.path.expanduser("~/.hermes"),
        )
    except Exception:
        pass  # 价格刷新失败不阻断扫描

    # Step 2: 运行卖出提醒扫描
    from src.analysis.sell_alert import scan_sell_alerts, SellAlert

    alerts = scan_sell_alerts()

    # Step 3: 过滤 — 仅 CRITICAL 和 WARNING
    important = [a for a in alerts if a.severity in ("CRITICAL", "WARNING")]

    if not important:
        # 无重要提醒, 静默退出 (不输出 = 不推送)
        return

    # Step 4: 输出提醒 (触发推送)
    severity_icons = {"CRITICAL": "🔴", "WARNING": "🟡"}

    print("⚠️ 意怠卖出提醒")
    print()

    for a in important:
        icon = severity_icons.get(a.severity, "⚪")
        print(f"{icon} [{a.severity}] {a.name} ({a.ticker})")
        print(f"   触发: {a.trigger_cn}")
        print(f"   当前价: {a.current_price}  成本: {a.cost_basis}  浮盈: {a.pnl_pct:+.1%}")
        print(f"   建议: {a.suggested_action}")
        if a.details:
            print(f"   备注: {a.details}")
        print()

    c_count = sum(1 for a in important if a.severity == "CRITICAL")
    w_count = sum(1 for a in important if a.severity == "WARNING")
    print(f"共 {len(important)} 条提醒: 🔴{c_count} 🟡{w_count}")

    if c_count > 0:
        print("⚠️ 有CRITICAL级提醒, 建议开盘后立即处理!")


if __name__ == "__main__":
    main()
