#!/usr/bin/env python3
"""测试 reason_taxonomy 模块。"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategy.reason_taxonomy import (
    classify_reason, ReasonCategory, SellReason,
    all_categories, all_sell_reasons,
)


def test_buy_classification():
    """买入分类测试。"""
    cases = [
        ("低位加仓摊低成本", ReasonCategory.LOW_PRICE_OPPORTUNITY),
        ("低位回补", ReasonCategory.LOW_PRICE_OPPORTUNITY),
        ("建仓/加仓", ReasonCategory.PORTFOLIO_REBALANCE),
        ("核心仓位建仓", ReasonCategory.PORTFOLIO_REBALANCE),
        ("分散投资建仓", ReasonCategory.PORTFOLIO_REBALANCE),
        ("短线波段交易", ReasonCategory.TECHNICAL_SETUP),
        ("财报超预期买入", ReasonCategory.EARNINGS_BEAT),
        ("AI主题投资", ReasonCategory.AI_THEME),
    ]
    for reason, expected in cases:
        cat, sell = classify_reason(reason, "BUY")
        assert cat == expected, f"'{reason}' → {cat}, expected {expected}"
        assert sell is None
    print(f"✓ 买入分类: {len(cases)} 项全部通过")


def test_sell_classification():
    """卖出分类测试。"""
    cases = [
        ("获利了结", SellReason.PROFIT_TAKING),
        ("部分减仓获利", SellReason.PROFIT_TAKING),  # "获利"优先匹配
        ("清仓退出", SellReason.EXIT),
        ("卖出", SellReason.EXIT),
        ("止损卖出", SellReason.STOP_LOSS),
    ]
    for reason, expected in cases:
        cat, sell = classify_reason(reason, "SELL")
        assert sell == expected, f"'{reason}' → {sell}, expected {expected}"
        assert cat is None
    print(f"✓ 卖出分类: {len(cases)} 项全部通过")


def test_reduce_classification():
    """REDUCE 动作也应走卖出分类。"""
    cat, sell = classify_reason("部分减仓获利", "REDUCE")
    assert cat is None
    assert sell is not None
    print(f"✓ REDUCE分类: {sell.value}")


def test_enums():
    """枚举值完整。"""
    cats = all_categories()
    reasons = all_sell_reasons()
    assert len(cats) == 10, f"Expected 10 categories, got {len(cats)}"
    assert len(reasons) == 8, f"Expected 8 sell reasons, got {len(reasons)}"
    print(f"✓ 枚举: {len(cats)} 催化剂 + {len(reasons)} 卖出原因")


def test_empty():
    """空值处理。"""
    cat, sell = classify_reason("", "BUY")
    assert cat is None and sell is None
    cat, sell = classify_reason("", "SELL")
    assert cat is None and sell is None
    print("✓ 空值处理通过")


if __name__ == "__main__":
    test_buy_classification()
    test_sell_classification()
    test_reduce_classification()
    test_enums()
    test_empty()
    print("\n✅ 所有测试通过")
