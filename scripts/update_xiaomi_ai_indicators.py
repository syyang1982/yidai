#!/usr/bin/env python3
"""
意怠工程 — 每周AI领先指标更新脚本

功能：
1. 从小米AI新闻搜索结果中提取关键数据点
2. 更新领先指标数据库
3. 输出变化摘要

用法：
    # 由 cron job agent 调用，传入 JSON 数据
    python scripts/update_xiaomi_ai_indicators.py --data '{"news_count": 5, "positive_count": 3, "ai_products": ["MiLM-2发布"], "xiaoai_mau": 1.68}'

    # 或直接更新单个指标
    python scripts/update_xiaomi_ai_indicators.py --indicator "AI新闻情绪" --value 65 --period "2026-W35"
"""

import sys
import os
import json
import argparse
from datetime import date, datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.analysis.leading_indicators import LeadingIndicatorStore

TICKER = "01810.HK"
COMPANY_NAME = "小米"


def update_indicator(store, indicator_name, value, period):
    """Update a single indicator value."""
    try:
        result = store.update_value(TICKER, indicator_name, value, period)
        status = result.get("status", "unknown")
        emoji = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}.get(status, "⚪")
        print(f"  {emoji} {indicator_name}: {value} [{status}] (period: {period})")
        return result
    except ValueError as e:
        print(f"  ⚠️ {indicator_name}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="更新小米AI领先指标")
    parser.add_argument("--data", type=str, help="JSON数据(news_count, positive_count, ai_products, xiaoai_mau)")
    parser.add_argument("--indicator", type=str, help="单个指标名称")
    parser.add_argument("--value", type=float, help="指标值")
    parser.add_argument("--period", type=str, default=date.today().strftime("%Y-W%W"), help="期间标识")
    parser.add_argument("--list", action="store_true", help="列出所有小米领先指标")
    args = parser.parse_args()

    store = LeadingIndicatorStore()

    if args.list:
        indicators = store.get_indicators(TICKER)
        print(f"\n📊 小米 ({TICKER}) 领先指标一览")
        print("=" * 70)
        for ind in indicators:
            status = ind.get("status", "neutral")
            emoji = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}.get(status, "⚪")
            value = ind.get("latest_value", "N/A")
            period = ind.get("latest_period", "N/A")
            unit = ind.get("unit", "")
            name = ind.get("indicator_name", "")
            category = ind.get("category", "")
            print(f"  {emoji} [{category}] {name}: {value} {unit} ({period})")
        store.close()
        return

    if args.indicator and args.value is not None:
        # 单指标更新模式
        print(f"\n📊 更新小米AI指标 ({args.period})")
        print("-" * 40)
        update_indicator(store, args.indicator, args.value, args.period)
        store.close()
        return

    if args.data:
        # 批量更新模式 (从 cron job agent 传入)
        data = json.loads(args.data)
        period = args.period

        print(f"\n📊 小米AI领先指标周度更新 ({period})")
        print("=" * 50)

        # 1. AI新闻情绪
        news_count = data.get("news_count", 0)
        positive_count = data.get("positive_count", 0)
        if news_count > 0:
            sentiment_pct = round(positive_count / news_count * 100, 1)
            update_indicator(store, "AI新闻情绪", sentiment_pct, period)
            print(f"    (基于 {news_count} 条新闻, {positive_count} 条正面)")

        # 2. AI产品发布数
        ai_products = data.get("ai_products", [])
        if ai_products:
            update_indicator(store, "AI产品发布数", len(ai_products), period)
            for p in ai_products:
                print(f"    📦 {p}")

        # 3. 小爱同学月活 (如果有新数据)
        xiaoai_mau = data.get("xiaoai_mau")
        if xiaoai_mau:
            update_indicator(store, "小爱同学月活", xiaoai_mau, period)

        # 输出当前全部指标状态
        print(f"\n{'=' * 50}")
        indicators = store.get_indicators(TICKER)
        ai_indicators = [i for i in indicators if i.get("category") in ("AI用户", "AI进展")]
        if ai_indicators:
            print("AI相关指标汇总:")
            for ind in ai_indicators:
                status = ind.get("status", "neutral")
                emoji = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}.get(status, "⚪")
                value = ind.get("latest_value", "N/A")
                unit = ind.get("unit", "")
                name = ind.get("indicator_name", "")
                updated = ind.get("latest_date", "N/A")
                print(f"  {emoji} {name}: {value} {unit} (更新: {updated})")

        store.close()
        print(f"\n✅ 更新完成")
        return

    # 无参数时显示帮助
    parser.print_help()
    store.close()


if __name__ == "__main__":
    main()
