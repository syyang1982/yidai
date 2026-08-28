"""Batch import leading indicators for watchlist companies.

Imports all leading indicators from the watchlist into the
LeadingIndicatorStore database.

Usage:
    python scripts/import_leading_indicators.py
"""

import sys
import os

# Ensure project root is on path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.analysis.leading_indicators import LeadingIndicatorStore

# --- Indicator definitions ---
# Format: (indicator_name, description, source, threshold_positive, threshold_negative, unit, category)
# threshold_positive/threshold_negative default to None if not specified in watchlist.

COMPANIES = [
    # 1. 铖昌科技 001270.SZ
    {
        "ticker": "001270.SZ",
        "company_name": "铖昌科技",
        "category": "卫星互联网",
        "indicators": [
            ("星网月发射数", "星网月度卫星发射数量", "公告", 30, None, "颗/月", "业务进展"),
            ("营收增速", "营收同比增长率", "季报", 30, 10, "%", "财务"),
        ],
    },
    # 2. 来福谐波 301528.SZ
    {
        "ticker": "301528.SZ",
        "company_name": "来福谐波",
        "category": "机器人核心零部件",
        "indicators": [
            ("月度出货量", "谐波减速器月度出货量", "月度数据", None, None, "台", "业务进展"),
            ("新客户导入数", "新客户导入数量", "公告", 3, None, "家/季度", "客户拓展"),
        ],
    },
    # 3. 海康威视 002415.SZ
    {
        "ticker": "002415.SZ",
        "company_name": "海康威视",
        "category": "安防/AI",
        "indicators": [
            ("营收增速", "营收同比增长率", "季报", 5, 0, "%", "财务"),
            ("海外收入占比", "海外收入占总收入比例", "季报", 35, None, "%", "收入结构"),
            ("创新业务收入占比", "创新业务收入占总收入比例", "季报", 20, None, "%", "收入结构"),
        ],
    },
    # 4. 英维克 002837.SZ
    {
        "ticker": "002837.SZ",
        "company_name": "英维克",
        "category": "液冷散热",
        "indicators": [
            ("液冷订单增速", "液冷相关订单同比增长率", "季报", 50, None, "%", "业务进展"),
            ("液冷收入占比", "液冷业务收入占总收入比例", "季报", 30, None, "%", "收入结构"),
        ],
    },
    # 5. 海光信息 688041.SH
    {
        "ticker": "688041.SH",
        "company_name": "海光信息",
        "category": "国产算力",
        "indicators": [
            ("DCU出货量", "国产GPU/DCU出货量", "季报", None, None, "颗", "业务进展"),
        ],
    },
    # 6. 工业富联 601138.SS
    {
        "ticker": "601138.SS",
        "company_name": "工业富联",
        "category": "AI服务器",
        "indicators": [
            ("AI服务器毛利率", "AI服务器业务毛利率", "季报", 8, 5, "%", "财务"),
        ],
    },
    # 7. 中际旭创 300308.SZ
    {
        "ticker": "300308.SZ",
        "company_name": "中际旭创",
        "category": "光模块",
        "indicators": [
            ("800G出货量", "800G光模块出货量", "季报", None, None, "只", "业务进展"),
        ],
    },
    # 8. 中创新航 03931.HK
    {
        "ticker": "03931.HK",
        "company_name": "中创新航",
        "category": "动力电池",
        "indicators": [
            ("产能利用率", "电池产能利用率", "季报", 80, 60, "%", "运营"),
            ("小米车型交付量", "为小米车型配套电池交付量", "公告", None, None, "套", "业务进展"),
        ],
    },
    # 9. 永辉超市 601933.SH
    {
        "ticker": "601933.SH",
        "company_name": "永辉超市",
        "category": "零售",
        "indicators": [
            ("同店增长率", "同店销售同比增长率", "季报", 10, 0, "%", "财务"),
            ("毛利率", "综合毛利率", "季报", 22, 20, "%", "财务"),
        ],
    },
    # 10. 万国数据 09698.HK
    {
        "ticker": "09698.HK",
        "company_name": "万国数据",
        "category": "数据中心",
        "indicators": [
            ("季度新签MW", "季度新签约数据中心容量", "季报", 100, None, "MW", "业务进展"),
            ("AI客户收入占比", "AI相关客户收入占总收入比例", "季报", 40, None, "%", "收入结构"),
            ("上架率", "数据中心机柜上架率", "季报", 75, None, "%", "运营"),
        ],
    },
    # 11. 赣锋锂业 002460.SZ
    {
        "ticker": "002460.SZ",
        "company_name": "赣锋锂业",
        "category": "锂电材料",
        "indicators": [
            ("碳酸锂价格", "碳酸锂市场价格", "市场数据", 100000, 70000, "元/吨", "商品价格"),
            ("毛利率", "综合毛利率", "季报", 20, 5, "%", "财务"),
        ],
    },
    # 12. 杭氧股份 002430.SZ
    {
        "ticker": "002430.SZ",
        "company_name": "杭氧股份",
        "category": "工业气体",
        "indicators": [
            ("提氦项目招标数", "提氦相关项目招标数量", "行业数据", 5, None, "个/半年", "业务进展"),
        ],
    },
    # 13. 华特气体 688268.SH
    {
        "ticker": "688268.SH",
        "company_name": "华特气体",
        "category": "特种气体",
        "indicators": [
            ("产能利用率", "特种气体产能利用率", "季报", 80, None, "%", "运营"),
        ],
    },
]


def main():
    """Import all leading indicators and print results."""
    store = LeadingIndicatorStore()

    total = 0
    errors = 0

    print("=" * 70)
    print("领先指标批量导入")
    print("=" * 70)
    print()

    for company in COMPANIES:
        ticker = company["ticker"]
        company_name = company["company_name"]
        category = company["category"]

        print(f"📦 {company_name} ({ticker})")

        for ind in company["indicators"]:
            ind_name, description, source, thresh_pos, thresh_neg, unit, ind_category = ind
            try:
                result = store.add_indicator(
                    ticker=ticker,
                    company_name=company_name,
                    indicator_name=ind_name,
                    description=description,
                    source=source,
                    threshold_positive=thresh_pos,
                    threshold_negative=thresh_neg,
                    unit=unit,
                    category=ind_category,
                )
                status_info = f"[{result.get('status', 'neutral')}]"
                print(f"   ✅ {ind_name} {status_info}")
                total += 1
            except Exception as e:
                print(f"   ❌ {ind_name}: {e}")
                errors += 1

        print()

    # Summary
    print("=" * 70)
    print(f"导入完成: {total} 条指标已导入, {errors} 条失败")
    print("=" * 70)

    # Verification
    print("\n📊 验证: 数据库中的指标总数")
    all_indicators = store.get_indicators()
    print(f"   数据库中共有 {len(all_indicators)} 条领先指标")

    # Count by company
    from collections import Counter
    ticker_counts = Counter(ind["ticker"] for ind in all_indicators)
    print("\n   按公司分布:")
    for ticker, count in ticker_counts.items():
        name = next((c["company_name"] for c in COMPANIES if c["ticker"] == ticker), ticker)
        print(f"     {name} ({ticker}): {count} 条")

    store.close()
    print("\n✅ 脚本执行完成")


if __name__ == "__main__":
    main()
