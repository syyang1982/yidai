"""Portfolio configuration — default constraints and sample holdings for testing."""
from __future__ import annotations

from typing import List

from src.strategy.portfolio_constraints import PortfolioConstraints


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


def create_sample_holdings() -> List[dict]:
    """Return sample holdings data for testing.

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
