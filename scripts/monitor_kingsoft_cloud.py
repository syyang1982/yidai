#!/usr/bin/env python3
"""金山云领先指标监控脚本。

自动从eastmoney获取季度数据，更新领先指标状态。
合同负债和大客户CapEx需手动录入。
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
            result = store.update_value("3896.HK", "AI云收入增速", round(rev_yoy, 2), period)
            status = result.get("status", "?")
            print(f"  AI云收入增速: {rev_yoy:.1f}% [{status}]")
        except ValueError:
            print(f"  AI云收入增速: 指标未定义，请先运行 import_leading_indicators.py")
    else:
        print("  AI云收入增速: 无数据")

    # 2. 合同负债增速 (需手动录入)
    print("  合同负债增速: 需手动录入")

    # 3. 大客户CapEx (需手动录入)
    print("  大客户CapEx: 需手动录入")

    # 显示其他关键指标
    print(f"\n=== {period} 季度数据 ===")
    rev = latest.get("OPERATE_INCOME") or 0
    print(f"  营收: {rev / 1e8:.2f}亿")

    gm = latest.get("GROSS_PROFIT_RATIO")
    if gm is not None:
        print(f"  毛利率: {gm:.1f}%")

    ni = latest.get("HOLDER_PROFIT") or 0
    print(f"  净利: {ni / 1e8:.2f}亿")

    ocf = latest.get("NETCASH_OPERATE") or 0
    print(f"  经营现金流: {ocf / 1e8:.2f}亿")

    store.close()
    return latest


def main():
    print("=== 金山云领先指标监控 ===\n")
    rows = fetch_kingsoft_cloud_data()
    update_indicators(rows)

    print("\n=== 需要手动更新的指标 ===")
    print("  使用以下命令手动录入:")
    print('  python3 -c "')
    print("  from src.analysis.leading_indicators import LeadingIndicatorStore")
    print("  store = LeadingIndicatorStore('db/leading_indicators.duckdb')")
    print("  store.update_value('3896.HK', '合同负债增速', <值>, '<期间>')")
    print("  store.update_value('3896.HK', '大客户CapEx', <值>, '<期间>')")
    print('  "')


if __name__ == "__main__":
    main()
