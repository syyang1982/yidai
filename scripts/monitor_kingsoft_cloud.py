#!/usr/bin/env python3
"""金山云领先指标监控脚本。

自动从eastmoney获取季度数据，更新领先指标状态:
- AI云收入增速: 营收同比(eastmoney自动)
- 经营现金流/营收比: 现金流质量(自动计算)
- 大客户CapEx: 需手动录入
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from src.analysis.leading_indicators import LeadingIndicatorStore


def fetch_kingsoft_cloud_data():
    """从eastmoney获取金山云季度数据。"""
    url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    params = {
        "reportName": "RPT_HKF10_FN_MAININDICATOR",
        "columns": "ALL",
        "filter": '(SECUCODE="03896.HK")',
        "source": "F10",
        "client": "PC",
        "p": 1,
        "ps": 8,
        "sortTypes": "-1",
        "sortColumns": "REPORT_DATE",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = (data.get("result") or {}).get("data") or []
        return rows
    except Exception as e:
        print(f"获取数据失败: {e}")
        return []


def update_indicators(rows):
    """更新领先指标。"""
    db_path = os.path.expanduser("~/.hermes/yidai/db/leading_indicators.duckdb")
    store = LeadingIndicatorStore(db_path)

    if not rows:
        print("无数据可更新")
        return

    latest = rows[0]
    period = (latest.get("REPORT_DATE") or "")[:10]

    # 1. AI云收入增速 (用营收同比代替)
    rev_yoy = latest.get("OPERATE_INCOME_YOY")
    if rev_yoy is not None:
        try:
            store.update_value("3896.HK", "AI云收入增速", round(rev_yoy, 2), period)
            print(f"  AI云收入增速: {rev_yoy:.1f}%")
        except ValueError:
            print(f"  AI云收入增速: 指标未定义")
    else:
        print("  AI云收入增速: 无数据")

    # 2. 经营现金流/营收比 (自动计算)
    rev = latest.get("OPERATE_INCOME") or 0
    ocf = latest.get("NETCASH_OPERATE") or 0
    ocf_ratio = 0.0
    if rev > 0:
        ocf_ratio = round(ocf / rev * 100, 2)
        try:
            store.update_value("3896.HK", "经营现金流营收比", ocf_ratio, period)
            print(f"  经营现金流/营收比: {ocf_ratio:.1f}%")
        except ValueError:
            print(f"  经营现金流/营收比: 指标未定义")
    else:
        print("  经营现金流/营收比: 营收为0")

    # 3. 大客户CapEx (需手动录入)
    print("  大客户CapEx: 需手动录入")

    # 显示关键指标
    print(f"\n=== {period} 季度数据 ===")
    if rev:
        print(f"  营收: {rev / 1e8:.2f}亿")

    gm = latest.get("GROSS_PROFIT_RATIO")
    if gm is not None:
        print(f"  毛利率: {gm:.1f}%")

    ni = latest.get("HOLDER_PROFIT") or 0
    print(f"  净利: {ni / 1e8:.2f}亿")

    if ocf:
        print(f"  经营现金流: {ocf / 1e8:.2f}亿")

    # 历史对比(如果有前几期数据)
    if len(rows) >= 2:
        prev = rows[1]
        prev_period = (prev.get("REPORT_DATE") or "")[:10]
        prev_ocf = prev.get("NETCASH_OPERATE") or 0
        prev_rev = prev.get("OPERATE_INCOME") or 0
        if prev_rev > 0 and prev_ocf:
            prev_ratio = prev_ocf / prev_rev * 100
            print(f"\n  对比 {prev_period}:")
            print(f"    经营现金流/营收比: {prev_ratio:.1f}% → {ocf_ratio:.1f}%")
            if ocf_ratio > prev_ratio:
                print(f"    趋势: ↑ 改善")
            elif ocf_ratio < prev_ratio:
                print(f"    趋势: ↓ 恶化")
            else:
                print(f"    趋势: → 持平")


def main():
    print("=== 金山云领先指标监控 ===\n")
    rows = fetch_kingsoft_cloud_data()
    update_indicators(rows)

    print("\n=== 需要手动更新的指标 ===")
    print("  使用以下命令手动录入:")
    print('  python3 -c "')
    print("  from src.analysis.leading_indicators import LeadingIndicatorStore")
    print("  store = LeadingIndicatorStore('db/leading_indicators.duckdb')")
    print("  store.update_value('3896.HK', '大客户CapEx', <值>, '<期间>')")
    print('  "')


if __name__ == "__main__":
    main()
