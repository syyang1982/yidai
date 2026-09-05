"""市场环境(Regime)检测模块。

基于持仓/观察清单公司的平均动量判断当前市场环境:
  - BULL: 平均6月动量 > +15%
  - BEAR: 平均6月动量 < -15%
  - NEUTRAL: 其他

用途:
  1. 调整BUY/REDUCE信号阈值
  2. 风险提示
  3. 仓位管理参考

数据来源: portfolio_data.json中的实时价格 + Yahoo Finance历史价格
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

import requests

PORTFOLIO_PATH = Path.home() / ".hermes" / "portfolio_data.json"

# 核心持仓/观察清单ticker (用于计算市场regime)
# 选择流动性好、有代表性的公司
_REGIME_TICKERS = {
    "1810.HK": "小米", "9988.HK": "阿里", "0700.HK": "腾讯",
    "9999.HK": "网易", "9626.HK": "B站", "2020.HK": "安踏",
    "002352.SZ": "顺丰", "600519.SS": "茅台", "300750.SZ": "宁德",
}


def _fetch_monthly_prices(ticker: str, months: int = 12) -> list[dict]:
    """从Yahoo Finance获取月度价格。"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1mo&range={months}mo"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = r.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        from datetime import datetime, timezone
        return [
            {"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m"),
             "close": round(c, 4)}
            for ts, c in zip(timestamps, closes) if c is not None
        ]
    except Exception:
        return []


def compute_momentum_6m(prices: list[dict]) -> Optional[float]:
    """计算最近6个月的价格动量。"""
    if len(prices) < 7:
        return None
    p_now = prices[-1]["close"]
    p_6m = prices[-7]["close"]
    if p_6m <= 0:
        return None
    return (p_now - p_6m) / p_6m


def get_market_regime(tickers: Optional[dict] = None) -> dict:
    """获取当前市场环境。

    Returns:
        dict with keys:
        - regime: "BULL" / "BEAR" / "NEUTRAL"
        - avg_momentum: float (average 6-month momentum)
        - details: dict of per-ticker momentums
        - date: str (evaluation date)
    """
    if tickers is None:
        tickers = _REGIME_TICKERS

    momentums = {}
    for ticker in tickers:
        prices = _fetch_monthly_prices(ticker, months=12)
        m6 = compute_momentum_6m(prices)
        if m6 is not None:
            momentums[ticker] = m6

    if not momentums:
        return {
            "regime": "NEUTRAL",
            "avg_momentum": 0.0,
            "details": {},
            "date": date.today().isoformat(),
            "note": "数据获取失败,默认NEUTRAL",
        }

    avg_m = sum(momentums.values()) / len(momentums)

    if avg_m > 0.15:
        regime = "BULL"
    elif avg_m < -0.15:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    return {
        "regime": regime,
        "avg_momentum": round(avg_m, 4),
        "details": {t: round(m, 4) for t, m in momentums.items()},
        "date": date.today().isoformat(),
    }


def get_regime_adjustments(regime: str) -> dict:
    """根据市场regime返回信号阈值调整。

    Returns:
        dict with:
        - buy_threshold_delta: int (add to buy threshold, positive=harder)
        - pe_cap_adjustment: float (multiply pe_cap, <1= stricter)
        - reduce_threshold_delta: int (add to reduce threshold, negative=easier)
    """
    if regime == "BEAR":
        return {
            "buy_threshold_delta": 2,      # 更难触发BUY
            "pe_cap_adjustment": 0.875,    # PE上限从80%降到70%
            "reduce_threshold_delta": -1,  # 更容易触发REDUCE
            "note": "熊市模式: 收紧买入, 放宽卖出",
        }
    elif regime == "BULL":
        return {
            "buy_threshold_delta": -1,     # 更容易触发BUY
            "pe_cap_adjustment": 1.0625,   # PE上限从80%升到85%
            "reduce_threshold_delta": 1,   # 更难触发REDUCE
            "note": "牛市模式: 放宽买入, 收紧卖出",
        }
    else:
        return {
            "buy_threshold_delta": 0,
            "pe_cap_adjustment": 1.0,
            "reduce_threshold_delta": 0,
            "note": "中性模式: 默认阈值",
        }


def format_regime_report(regime_data: dict) -> str:
    """格式化市场regime报告。"""
    regime = regime_data["regime"]
    avg_m = regime_data["avg_momentum"]
    icons = {"BULL": "🟢", "BEAR": "🔴", "NEUTRAL": "🟡"}
    icon = icons.get(regime, "⚪")

    lines = [
        f"  {icon} 市场环境: {regime} (平均6月动量: {avg_m:+.1%})",
        "",
    ]

    details = regime_data.get("details", {})
    if details:
        lines.append("  各公司6月动量:")
        for ticker, m in sorted(details.items(), key=lambda x: x[1]):
            indicator = "↑" if m > 0 else "↓"
            lines.append(f"    {ticker:12s} {m:+.1%} {indicator}")
        lines.append("")

    adjustments = get_regime_adjustments(regime)
    lines.append(f"  信号调整: {adjustments['note']}")

    return "\n".join(lines)
