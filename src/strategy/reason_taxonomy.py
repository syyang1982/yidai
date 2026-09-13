"""
决策理由分类体系 — 意怠工程 (Yidai)

将自由文本的决策理由标准化为两个维度：
1. reason_category — 买入决策的催化剂/论点类型
2. sell_reason — 卖出/减仓的具体原因

设计原则：
- 面向个人投资者，不是机构
- 分类基于实际交易记录的模式
- 支持从自由文本自动匹配到分类标签
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ReasonCategory(str, Enum):
    """买入决策的催化剂/论点分类。

    用于回答：这笔买入是什么驱动的？
    """
    # 催化剂驱动
    EARNINGS_BEAT = "财报超预期"        # 财报/业绩超预期
    POLICY_TAILWIND = "政策利好"        # 政策面利好
    PRODUCT_LAUNCH = "产品发布"         # 新产品/服务发布
    INDUSTRY_INFLECTION = "行业拐点"    # 行业周期拐点
    VALUATION_RECOVERY = "估值修复"     # 估值从低估修复
    TECHNICAL_SETUP = "技术形态"        # 技术面信号
    AI_THEME = "AI主题"                 # AI/科技主题驱动

    # 机会驱动
    LOW_PRICE_OPPORTUNITY = "低位机会"   # 价格跌到低位，摊低成本/回补

    # 组合管理
    PORTFOLIO_REBALANCE = "组合再平衡"   # 分散投资、建核心仓位
    POSITION_BUILDING = "建仓/加仓"     # 通用建仓加仓（无特定催化）


class SellReason(str, Enum):
    """卖出/减仓原因分类。

    仅适用于 action 为 SELL 或 REDUCE 的决策。
    """
    PROFIT_TAKING = "获利了结"          # 盈利后卖出锁定收益
    STOP_LOSS = "止损"                  # 亏损后止损
    CATALYST_FAILED = "催化剂落空"      # 预期催化剂未兑现
    FUNDAMENTAL_DETERIORATION = "基本面恶化"  # 财务/业务恶化
    POSITION_REBALANCE = "仓位再平衡"   # 调整持仓比例
    CAPITAL_NEED = "资金需求"           # 需要资金用于其他用途
    OVERVALUED = "估值过高"             # 估值过高，泡沫
    EXIT = "清仓退出"                   # 完全清仓（通用）


# ── 自动分类规则 ──────────────────────────────────────────────
# 按优先级排列：越具体的规则越靠前

_BUY_RULES: list[tuple[list[str], ReasonCategory]] = [
    # 低位机会
    (["低位", "摊低成本", "回补", "补仓"], ReasonCategory.LOW_PRICE_OPPORTUNITY),
    # 催化剂驱动
    (["财报", "业绩", "超预期"], ReasonCategory.EARNINGS_BEAT),
    (["政策", "利好"], ReasonCategory.POLICY_TAILWIND),
    (["产品", "发布", "新品"], ReasonCategory.PRODUCT_LAUNCH),
    (["行业拐点", "周期"], ReasonCategory.INDUSTRY_INFLECTION),
    (["估值", "修复", "低估"], ReasonCategory.VALUATION_RECOVERY),
    (["技术", "形态", "突破", "均线"], ReasonCategory.TECHNICAL_SETUP),
    (["AI", "人工智能"], ReasonCategory.AI_THEME),
    # 组合管理
    (["分散", "核心仓位", "建仓"], ReasonCategory.PORTFOLIO_REBALANCE),
    # 通用
    (["短线", "波段", "交易"], ReasonCategory.TECHNICAL_SETUP),
]

_SELL_RULES: list[tuple[list[str], SellReason]] = [
    (["获利", "盈利", "收益"], SellReason.PROFIT_TAKING),
    (["止损", "亏损"], SellReason.STOP_LOSS),
    (["清仓", "退出"], SellReason.EXIT),
    (["催化剂", "落空", "未兑现"], SellReason.CATALYST_FAILED),
    (["恶化", "下滑", "暴雷"], SellReason.FUNDAMENTAL_DETERIORATION),
    (["再平衡", "仓位", "减仓", "部分"], SellReason.POSITION_REBALANCE),
    (["资金", "需求", "用钱"], SellReason.CAPITAL_NEED),
    (["过高", "泡沫", "高估"], SellReason.OVERVALUED),
    # 通用卖出
    (["卖出"], SellReason.EXIT),
]


def classify_reason(reason: str, action: str = "BUY") -> tuple[Optional[ReasonCategory], Optional[SellReason]]:
    """根据自由文本理由自动分类。

    Args:
        reason: 原始自由文本理由
        action: 交易动作 (BUY/SELL/REDUCE/ADD/HOLD)

    Returns:
        (reason_category, sell_reason)
        - BUY/ADD/HOLD: reason_category 填充, sell_reason=None
        - SELL/REDUCE: reason_category=None, sell_reason 填充
    """
    if not reason:
        return (None, None)

    reason_lower = reason.strip()

    if action in ("SELL", "REDUCE"):
        for keywords, category in _SELL_RULES:
            if any(kw in reason_lower for kw in keywords):
                return (None, category)
        return (None, SellReason.EXIT)  # 默认
    else:
        for keywords, category in _BUY_RULES:
            if any(kw in reason_lower for kw in keywords):
                return (category, None)
        return (ReasonCategory.POSITION_BUILDING, None)  # 默认


def category_label(cat: ReasonCategory) -> str:
    """返回分类的中文标签。"""
    return cat.value


def sell_reason_label(reason: SellReason) -> str:
    """返回卖出原因的中文标签。"""
    return reason.value


def all_categories() -> list[dict]:
    """列出所有买入催化剂分类。"""
    return [{"key": c.name, "label": c.value} for c in ReasonCategory]


def all_sell_reasons() -> list[dict]:
    """列出所有卖出原因分类。"""
    return [{"key": r.name, "label": r.value} for r in SellReason]
