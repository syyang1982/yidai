"""Portfolio configuration — constraint defaults + real portfolio loading.

历史坑（2026-09-22 修复）：`create_sample_holdings()` 是**演示数据**，
曾被 `manage.py constraints` 直接当作真实持仓使用，导致单股仓位检查永远
报"✅ 均在限内"（当时小米实际占 61.1%，远超 30% 硬约束却显示合规）。

现在约束检查默认走 :func:`load_real_holdings`（读 ``~/.hermes/portfolio_data.json``），
只有真实数据不可用时才回退到示例数据，并且会明确标注，不再伪装成真实结果。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

from src.strategy.portfolio_constraints import PortfolioConstraints

PORTFOLIO_JSON = os.path.expanduser("~/.hermes/portfolio_data.json")

#: ticker → (行业, 市场)。portfolio_data.json 不存行业，这里集中维护。
SECTOR_MAP: Dict[str, Tuple[str, str]] = {
    "01810.HK": ("科技", "港股"), "1810.HK": ("科技", "港股"),
    "3888.HK":  ("科技", "港股"), "03888.HK": ("科技", "港股"),
    "3896.HK":  ("科技", "港股"), "03896.HK": ("科技", "港股"),
    "09988.HK": ("科技", "港股"), "9988.HK": ("科技", "港股"),
    "9999.HK":  ("科技", "港股"), "09999.HK": ("科技", "港股"),
    "9626.HK":  ("科技", "港股"), "09626.HK": ("科技", "港股"),
    "2498.HK":  ("科技", "港股"), "02498.HK": ("科技", "港股"),
    "2252.HK":  ("医疗", "港股"), "02252.HK": ("医疗", "港股"),
    "2020.HK":  ("消费", "港股"), "02020.HK": ("消费", "港股"),
    "2097.HK":  ("消费", "港股"), "02097.HK": ("消费", "港股"),
    "9896.HK":  ("消费", "港股"), "09896.HK": ("消费", "港股"),
    "1361.HK":  ("消费", "港股"), "01361.HK": ("消费", "港股"),
    "LX":       ("金融", "美股"),
    "SGP.AX":   ("地产", "澳洲"), "SGP.ASX": ("地产", "澳洲"),
    "002352.SZ": ("物流", "A股"),
    "600933.SH": ("制造", "A股"),
}

#: 汇率：1 单位本币 = ? HKD 的倒数口径（与 portfolio_data.json 一致：
#:   xxx_PER_HKD 表示 1 HKD 折多少本币，换算本币→HKD 是除以该值）
DEFAULT_RATES = {"CNY_PER_HKD": 0.872489, "USD_PER_HKD": 0.1282, "AUD_PER_HKD": 0.17936}

#: 已知币种（用于缺汇率告警）。注意存的是**币种代码**，不是 "XXX_PER_HKD" 键名。
_KNOWN_CCY = {"HKD", "CNY", "USD", "AUD"}


def get_default_constraints() -> PortfolioConstraints:
    """Return a PortfolioConstraints pre-loaded with default limits and correlation groups."""
    pc = PortfolioConstraints(
        max_single_pct=25.0,
        max_sector_pct=40.0,
        max_market_pct=70.0,
        max_correlation_group_pct=35.0,
    )

    # ── Correlation groups ─────────────────────────────────────────
    pc.add_correlation_group(
        "金山系",
        ["3888.HK", "3896.HK"],
        "同一控股公司(金山集团)",
    )
    pc.add_correlation_group(
        "小米生态",
        ["01810.HK", "3896.HK"],
        "小米是金山云核心客户+股东",
    )
    pc.add_correlation_group(
        "港股互联网",
        ["01810.HK", "9988.HK", "9999.HK", "9626.HK"],
        "港股互联网板块",
    )
    pc.add_correlation_group(
        "港股消费",
        ["2097.HK", "9896.HK", "1361.HK"],
        "港股消费板块",
    )

    return pc


# ── 汇率 ──────────────────────────────────────────────────────────────
def _rates(raw: dict) -> Dict[str, float]:
    rates = dict(DEFAULT_RATES)
    for k, v in (raw or {}).get("exchange_rates", {}).items():
        try:
            rates[k] = float(v)
        except (TypeError, ValueError):
            continue
    return rates


def to_hkd(amount: float, currency: str, rates: Dict[str, float]) -> float:
    """把 ``amount``（``currency`` 计价）换算成 HKD。

    本币→HKD 是**除以** ``xxx_PER_HKD``（该值表示 1 HKD 折多少本币）。
    未知币种原样返回并由调用方告警，绝不静默换算。
    """
    ccy = (currency or "HKD").upper()
    if ccy == "HKD":
        return float(amount)
    key = f"{ccy}_PER_HKD"
    if key not in rates or not rates[key]:
        return float(amount)
    return float(amount) / float(rates[key])


# ── 真实持仓 ──────────────────────────────────────────────────────────
def load_real_holdings(path: str = PORTFOLIO_JSON) -> Tuple[List[dict], List[str]]:
    """从 portfolio_data.json 读真实持仓，返回 (holdings, warnings)。

    输出的每条记录满足 :class:`PortfolioConstraints` 所需字段：
    ``ticker / name / value_hkd / sector / market``，另带
    ``cost_hkd / pnl_pct / current_price / stop_loss / signal`` 供风控预算检查用。
    零股持仓（已清仓）会被跳过——它不该占用仓位分母。
    """
    warnings: List[str] = []
    if not os.path.exists(path):
        return [], [f"找不到 {path}，无法加载真实持仓"]

    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return [], [f"解析 {path} 失败: {e}"]

    rates = _rates(raw)
    prices = raw.get("prices", {}) or {}
    targets = (raw.get("strategy", {}) or {}).get("sell_targets", {}) or {}
    signals = raw.get("signals", {}) or {}

    out: List[dict] = []
    _warned: set = set()
    for h in raw.get("holdings", []) or []:
        ticker = h.get("ticker", "")
        try:
            shares = float(h.get("shares", 0) or 0)
        except (TypeError, ValueError):
            shares = 0.0
        if shares <= 0:
            continue

        price_ccy = (h.get("price_ccy") or "HKD").upper()
        cost_ccy = (h.get("cost_ccy") or price_ccy).upper()
        for ccy in (price_ccy, cost_ccy):
            if ccy not in _KNOWN_CCY and (ticker, ccy) not in _warned:
                _warned.add((ticker, ccy))
                warnings.append(f"{ticker} 缺 {ccy} 汇率，市值按原币数值计入 HKD 汇总（会失真）")

        price = 0.0
        p = prices.get(ticker) or {}
        if isinstance(p, dict):
            price = float(p.get("price", 0) or 0)
        elif isinstance(p, (int, float)):
            price = float(p)
        if price <= 0:
            warnings.append(f"{ticker} 无有效现价，市值计为 0（会导致分母偏小、占比虚高）")

        try:
            avg_cost = float(h.get("avg_cost", 0) or 0)
        except (TypeError, ValueError):
            avg_cost = 0.0

        value_hkd = to_hkd(shares * price, price_ccy, rates)
        cost_hkd = to_hkd(shares * avg_cost, cost_ccy, rates)

        sector, market = SECTOR_MAP.get(ticker, ("未知", "未知"))
        tgt = targets.get(ticker, {}) or {}

        out.append({
            "ticker": ticker,
            "name": h.get("name", ticker),
            "shares": shares,
            "value_hkd": value_hkd,
            "cost_hkd": cost_hkd,
            "pnl_pct": ((value_hkd - cost_hkd) / cost_hkd * 100) if cost_hkd > 0 else 0.0,
            "current_price": price,
            "sector": sector,
            "market": market,
            "signal": signals.get(ticker),
            "stop_loss": tgt.get("stop_loss") or tgt.get("stop_loss_price"),
            "stop_loss_pct": tgt.get("stop_loss_pct"),
            "take_profit_pct": tgt.get("take_profit_pct"),
        })

    if not out:
        warnings.append("portfolio_data.json 中没有非零持仓")
    return out, warnings


def create_sample_holdings() -> List[dict]:
    """Return **sample** holdings data for testing.

    ⚠️ 这是演示数据，不是真实持仓。约束检查请用 :func:`load_real_holdings`。
    Total ≈ HK$1,000,000 with Xiaomi as the largest position (~20%).
    """
    return [
        {"ticker": "01810.HK", "name": "小米集团", "value_hkd": 200_000, "sector": "科技", "market": "港股"},
        {"ticker": "3896.HK",  "name": "金山云",   "value_hkd": 70_000,  "sector": "科技", "market": "港股"},
        {"ticker": "3888.HK",  "name": "金山软件", "value_hkd": 60_000,  "sector": "科技", "market": "港股"},
        {"ticker": "09988.HK", "name": "阿里巴巴", "value_hkd": 120_000, "sector": "科技", "market": "港股"},
        {"ticker": "9896.HK",  "name": "名创优品", "value_hkd": 50_000,  "sector": "消费", "market": "港股"},
        {"ticker": "9626.HK",  "name": "B站",      "value_hkd": 40_000,  "sector": "科技", "market": "港股"},
        {"ticker": "9999.HK",  "name": "网易",     "value_hkd": 60_000,  "sector": "科技", "market": "港股"},
        {"ticker": "2020.HK",  "name": "安踏体育", "value_hkd": 65_000,  "sector": "消费", "market": "港股"},
        {"ticker": "2252.HK",  "name": "微创机器人", "value_hkd": 55_000, "sector": "医疗", "market": "港股"},
        {"ticker": "2498.HK",  "name": "速腾聚创", "value_hkd": 45_000,  "sector": "科技", "market": "港股"},
        {"ticker": "1361.HK",  "name": "361度",    "value_hkd": 60_000,  "sector": "消费", "market": "港股"},
        {"ticker": "LX",       "name": "乐信",     "value_hkd": 110_000, "sector": "金融", "market": "美股"},
        {"ticker": "SGP.ASX",  "name": "Stockland","value_hkd": 65_000,  "sector": "地产", "market": "澳洲"},
    ]
