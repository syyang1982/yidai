"""Batch import leading indicators for portfolio + watchlist companies.

Focused on top 10 portfolio companies (2-3 core indicators each)
plus top watchlist companies.  Each indicator carries a dimension_map
linking its status to scorer dimension adjustments.

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
# Format: (indicator_name, description, source, threshold_positive,
#           threshold_negative, unit, ind_category, dimension_map)
#
# dimension_map: {"negative": {"<dim>": <adjustment>}, "positive": {"<dim>": <adjustment>}}
# Maps indicator status to scorer dimension adjustments.

# ── Portfolio companies (持仓) ──────────────────────────────────────────────

PORTFOLIO = [
    # 1. 小米 01810.HK
    {
        "ticker": "01810.HK",
        "company_name": "小米",
        "category": "消费电子/汽车",
        "indicators": [
            ("SU7月交付量", "小米SU7系列月度交付量", "月度数据", 15000, 8000, "辆/月", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("IoT收入增速", "IoT与生活消费品收入同比增长率", "季报", 20, 5, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("手机市占率", "全球智能手机市场份额", "季报数据", 14, 11, "%", "市场地位",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 2. 金山云 3896.HK
    {
        "ticker": "3896.HK",
        "company_name": "金山云",
        "category": "云计算/AI",
        "indicators": [
            ("AI云收入增速", "AI云业务收入同比增长率", "季报", 50, 20, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("大客户CapEx", "主要客户资本开支趋势(行业)", "季报/行业", 10, -5, "%", "需求端",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("合同负债增速", "合同负债同比增长率", "季报", 20, 0, "%", "财务",
             {"negative": {"cashflow": -1}, "positive": {"cashflow": 0.5}}),
        ],
    },
    # 3. 阿里 09988.HK
    {
        "ticker": "09988.HK",
        "company_name": "阿里巴巴",
        "category": "电商/云",
        "indicators": [
            ("云收入增速", "阿里云收入同比增长率", "季报", 10, 0, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("国际电商增速", "国际数字商业收入同比增长率", "季报", 25, 10, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("回购金额", "季度股份回购金额(亿美元)", "公告", 40, 10, "亿美元/季", "股东回报",
             {"negative": {"valuation": -1}, "positive": {"valuation": 0.5}}),
        ],
    },
    # 4. 网易 9999.HK
    {
        "ticker": "9999.HK",
        "company_name": "网易",
        "category": "游戏",
        "indicators": [
            ("游戏版号获取", "季度获得游戏版号数量", "公告", 3, 0, "个/季", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("海外收入占比", "海外游戏收入占游戏总收入比例", "季报", 15, 5, "%", "收入结构",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("新游流水", "新上线游戏月流水(亿元)", "行业数据", 5, 1, "亿元/月", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 5. 名创 9896.HK
    {
        "ticker": "9896.HK",
        "company_name": "名创优品",
        "category": "零售",
        "indicators": [
            ("同店增速", "同店销售同比增长率", "季报", 10, 0, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("海外门店数", "海外门店总数", "季报", 2500, 2000, "家", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("IP授权收入占比", "IP授权产品收入占总收入比例", "季报", 30, 15, "%", "收入结构",
             {"negative": {"profitability": -1}, "positive": {"profitability": 0.5}}),
        ],
    },
    # 6. B站 9626.HK
    {
        "ticker": "9626.HK",
        "company_name": "哔哩哔哩",
        "category": "互联网/视频",
        "indicators": [
            ("DAU增速", "日活跃用户同比增长率", "季报", 10, 3, "%", "用户",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("广告收入增速", "广告业务收入同比增长率", "季报", 20, 5, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("游戏收入", "游戏业务收入(亿元)", "季报", 15, 8, "亿元/季", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 7. 安踏 2020.HK
    {
        "ticker": "2020.HK",
        "company_name": "安踏体育",
        "category": "运动服饰",
        "indicators": [
            ("同店增速", "安踏品牌同店销售同比增长率", "季报", 8, 0, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("FILA增速", "FILA品牌收入同比增长率", "季报", 10, 0, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("海外收入占比", "海外收入占总收入比例", "季报", 15, 5, "%", "收入结构",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 8. 微创机器人 2252.HK
    {
        "ticker": "2252.HK",
        "company_name": "微创机器人",
        "category": "手术机器人",
        "indicators": [
            ("手术量增速", "机器人辅助手术量同比增长率", "季报", 30, 10, "%", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("海外收入占比", "海外收入占总收入比例", "季报", 15, 5, "%", "收入结构",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("新产品获批", "新产品获NMPA/FDA批准数量", "公告", 2, 0, "个/半年", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 9. 速腾聚创 2498.HK
    {
        "ticker": "2498.HK",
        "company_name": "速腾聚创",
        "category": "激光雷达",
        "indicators": [
            ("激光雷达出货量", "季度激光雷达出货量", "季报", 200000, 80000, "台/季", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("新客户导入", "新定点客户导入数量", "公告", 5, 1, "家/半年", "客户拓展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("车型定点数", "已定点量产车型数量", "公告", 50, 20, "个", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 10. 361度 1361.HK
    {
        "ticker": "1361.HK",
        "company_name": "361度",
        "category": "运动服饰",
        "indicators": [
            ("同店增速", "同店销售同比增长率", "季报", 8, 0, "%", "财务",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("电商收入占比", "电商收入占总收入比例", "季报", 25, 10, "%", "收入结构",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("海外门店数", "海外门店总数", "季报", 1500, 1000, "家", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
]

# ── Watchlist companies (观察清单) ──────────────────────────────────────────

WATCHLIST = [
    # 1. 来福谐波 301528.SZ
    {
        "ticker": "301528.SZ",
        "company_name": "来福谐波",
        "category": "机器人核心零部件",
        "indicators": [
            ("月度出货量", "谐波减速器月度出货量", "月度数据", None, None, "台", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("新客户导入数", "新客户导入数量", "公告", 3, None, "家/季度", "客户拓展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 2. 万国数据 09698.HK
    {
        "ticker": "09698.HK",
        "company_name": "万国数据",
        "category": "数据中心",
        "indicators": [
            ("季度新签MW", "季度新签约数据中心容量", "季报", 100, None, "MW", "业务进展",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("AI客户收入占比", "AI相关客户收入占总收入比例", "季报", 40, None, "%", "收入结构",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
        ],
    },
    # 3. 爱柯迪 600933.SH
    {
        "ticker": "600933.SH",
        "company_name": "爱柯迪",
        "category": "汽车零部件",
        "indicators": [
            ("新能源车订单占比", "新能源车相关订单占总订单比例", "季报", 50, 20, "%", "收入结构",
             {"negative": {"growth": -1}, "positive": {"growth": 0.5}}),
            ("产能利用率", "工厂产能利用率", "季报", 85, 65, "%", "运营",
             {"negative": {"health": -1}, "positive": {"health": 0.5}}),
        ],
    },
]

ALL_COMPANIES = PORTFOLIO + WATCHLIST


def main():
    """Import all leading indicators and print results."""
    store = LeadingIndicatorStore()

    total = 0
    errors = 0

    print("=" * 70)
    print("领先指标批量导入 (精简版: 持仓Top10 + 观察清单)")
    print("=" * 70)
    print()

    for company in ALL_COMPANIES:
        ticker = company["ticker"]
        company_name = company["company_name"]
        category = company["category"]

        print(f"📦 {company_name} ({ticker})")

        for ind in company["indicators"]:
            (ind_name, description, source, thresh_pos, thresh_neg,
             unit, ind_category, dimension_map) = ind
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
                    dimension_map=dimension_map,
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
        name = next((c["company_name"] for c in ALL_COMPANIES if c["ticker"] == ticker), ticker)
        print(f"     {name} ({ticker}): {count} 条")

    # Check dimension_map
    dm_count = sum(1 for ind in all_indicators if ind.get("dimension_map"))
    print(f"\n   带维度映射的指标: {dm_count}/{len(all_indicators)}")

    store.close()
    print("\n✅ 脚本执行完成")


if __name__ == "__main__":
    main()
