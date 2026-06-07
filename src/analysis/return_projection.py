"""回报预测模块 - 基于估值、增长和历史模式预测股票预期回报范围。"""


def project_returns(data: dict) -> dict:
    """Project expected returns for a stock.

    Args:
        data: dict with keys:
            - current_price: float
            - pe_ratio: float (current PE)
            - pe_history_percentile: float (0-1, where in PE history)
            - revenue_growth: float (decimal, e.g. 0.25 = 25%)
            - net_margin: float (decimal)
            - roe: float (decimal)
            - dividend_yield: float (decimal, e.g. 0.02 = 2%)
            - signal: str (BUY/HOLD/REDUCE)

    Returns:
        dict with projected return information.
    """
    pe = data.get("pe_ratio", 0) or 0
    pe_pct = data.get("pe_history_percentile", 0.5) or 0.5
    growth = data.get("revenue_growth", 0) or 0
    margin = data.get("net_margin", 0) or 0
    roe = data.get("roe", 0) or 0
    div = data.get("dividend_yield", 0) or 0
    signal = (data.get("signal") or "HOLD").upper()

    # Guard against PE <= 0
    earnings_yield = (1.0 / pe) if pe > 0 else 0.0

    drivers = []
    risks = []

    # Auto-generate drivers and risks
    if pe > 0 and pe < 15:
        drivers.append("低估值提供安全边际")
    if pe > 30:
        risks.append("高估值需要高增长支撑")
    if growth > 0.20:
        drivers.append("高增长是主要回报驱动")
    if growth < 0:
        risks.append("收入下滑影响盈利")
    if div > 0.03:
        drivers.append("股息提供稳定回报")
    if roe > 0.15:
        drivers.append("高ROE支撑长期回报")
    if margin < 0.05:
        risks.append("低利润率是风险因素")
    if pe_pct < 0.30:
        drivers.append("估值有均值回归空间")
    if pe_pct > 0.70:
        risks.append("估值有回调风险")

    if signal == "BUY":
        central, bull, bear, conf, reasoning = _buy_projection(
            earnings_yield, growth, pe_pct, div, pe, roe, margin
        )
    elif signal == "REDUCE":
        central, bull, bear, conf, reasoning = _reduce_projection(
            earnings_yield, growth, pe
        )
    else:  # HOLD
        central, bull, bear, conf, reasoning = _hold_projection(
            earnings_yield, div, pe, growth
        )

    ret_lo = min(bear, central, bull)
    ret_hi = max(bear, central, bull)
    return_range = f"{ret_lo:+.0%} ~ {ret_hi:+.0%}"

    return {
        "expected_12m_return": round(central, 4),
        "bull_case": round(bull, 4),
        "bear_case": round(bear, 4),
        "return_range": return_range,
        "key_drivers": drivers,
        "key_risks": risks,
        "confidence": conf,
        "reasoning": reasoning,
    }


def _buy_projection(earnings_yield, growth, pe_pct, div, pe, roe, margin):
    """BUY信号的回报预测。"""
    # PE reversion
    if pe_pct < 0.30:
        pe_reversion = 0.10 + (0.30 - pe_pct) * 0.5  # 10-20%
    elif pe_pct > 0.70:
        pe_reversion = -(0.10 + (pe_pct - 0.70) * 0.5)
    else:
        pe_reversion = 0.0

    growth_adjusted = growth * 0.5
    central = earnings_yield + growth_adjusted + pe_reversion + div

    bull = central + 0.5 * growth
    bear = central - 1.5 * growth

    # Confidence
    if pe < 15 and growth > 0.20 and roe > 0.15:
        conf = 5
    elif pe < 20 and growth > 0.10:
        conf = 4
    elif pe < 25 or growth > 0.10:
        conf = 3
    elif growth > 0.05:
        conf = 2
    else:
        conf = 1

    parts = [f"盈利收益率{earnings_yield:.1%}"]
    if growth_adjusted > 0:
        parts.append(f"增长贡献{growth_adjusted:.1%}")
    if pe_reversion != 0:
        parts.append(f"估值回归{pe_reversion:+.1%}")
    if div > 0:
        parts.append(f"股息{div:.1%}")
    reasoning = "买入预期: " + " + ".join(parts)

    return central, bull, bear, conf, reasoning


def _reduce_projection(earnings_yield, growth, pe):
    """REDUCE信号的回报预测。"""
    central = -(earnings_yield + growth * 0.3)
    bull = -0.05
    bear = -(growth + 0.20)

    conf = 2 if growth > 0.10 else 1

    reasoning = f"卖出预期: 估值偏高(PE {pe:.0f}), 预期回报为负"
    return central, bull, bear, conf, reasoning


def _hold_projection(earnings_yield, div, pe, growth):
    """HOLD信号的回报预测。"""
    central = earnings_yield + div
    spread = max(0.05, growth * 0.5)
    bull = central + spread
    bear = central - spread

    conf = 3

    parts = [f"盈利收益率{earnings_yield:.1%}"]
    if div > 0:
        parts.append(f"股息{div:.1%}")
    reasoning = "持有预期: " + " + ".join(parts) + ", 增长有限"
    return central, bull, bear, conf, reasoning


def format_projection(proj: dict, signal: str) -> str:
    """Format projection as markdown for inclusion in weekly report.
    Returns Chinese text with emoji indicators."""
    exp = proj["expected_12m_return"]
    bull = proj["bull_case"]
    bear = proj["bear_case"]
    conf = proj.get("confidence", 3)
    drivers = proj.get("key_drivers", [])
    risks = proj.get("key_risks", [])

    stars = "★" * conf + "☆" * (5 - conf)

    lines = [
        "📊 回报预期 (12个月):",
        f"  预期: {exp:+.0%}  乐观: {bull:+.0%}  悲观: {bear:+.0%}",
        f"  置信度: {stars}",
    ]
    if drivers:
        lines.append(f"  驱动因素: {', '.join(drivers)}")
    if risks:
        lines.append(f"  风险因素: {', '.join(risks)}")

    return "\n".join(lines)
