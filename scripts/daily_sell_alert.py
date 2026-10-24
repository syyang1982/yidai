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

    # Step 4: 输出提醒 — 按 report-format 规范（结论行动先行，正文≤300字）
    from datetime import date as _date
    severity_icons = {"CRITICAL": "🔴", "WARNING": "🟡"}

    c_count = sum(1 for a in important if a.severity == "CRITICAL")
    w_count = sum(1 for a in important if a.severity == "WARNING")
    # 最紧急的一条（CRITICAL 优先，其次浮亏最大）
    top = max(important, key=lambda a: (a.severity == "CRITICAL", abs(a.pnl_pct)))

    print(f"📌 意怠卖出提醒 — {_date.today().isoformat()}")
    print()
    print(f"【结论】{len(important)} 条待处理（🔴{c_count} 🟡{w_count}），"
          f"最要紧：{top.name} {severity_icons.get(top.severity)}")
    print()
    print("【行动】")
    for a in important:
        print(f"- {severity_icons.get(a.severity, '⚪')} {a.name}：{a.suggested_action}")
    print()
    print("【依据】")
    print("| 标的 | 级别 | 触发 | 现价 | 成本 | 浮盈 |")
    for a in important:
        lvl = "🔴CRIT" if a.severity == "CRITICAL" else "🟡WARN"
        trig = (a.trigger_cn or "")[:14]
        print(f"| {a.ticker} | {lvl} | {trig} | {a.current_price} | {a.cost_basis} | {a.pnl_pct:+.1%} |")
    for a in important:
        if a.details:
            print(f"  · {a.name}：{a.details}")
    if c_count > 0:
        print()
        print(f"【风险】含 {c_count} 条 CRITICAL，建议开盘后立即处理。")


if __name__ == "__main__":
    main()
