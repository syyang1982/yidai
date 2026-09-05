"""公司级信号权重配置 — 基于历史回测结果调整各公司的信号阈值。

回测发现不同公司的BUY信号表现差异巨大:
  - 小米: BUY信号T+12月+27% (优秀) → 放宽条件
  - 名创: BUY信号T+12月-43% (失败) → 收紧条件
  - 顺丰: BUY信号T+12月-18.5% (差) → 收紧条件

使用方式:
  config = get_company_config("1810.HK")
  config.buy_score_threshold  # 降低=更容易BUY
  config.pe_percentile_cap    # 降低=更严格估值要求
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class CompanySignalConfig:
    """单个公司的信号配置。"""
    ticker: str
    name: str = ""

    # BUY信号阈值调整 (默认=33)
    # 降低=更容易触发BUY, 升高=更难触发
    buy_score_threshold: int = 33

    # PE历史分位上限 (默认=0.80)
    # 降低=更严格估值要求
    pe_percentile_cap: float = 0.80

    # REDUCE后保护期天数 (默认=90)
    # 增加=更长的等待期
    reduce_protection_days: int = 90

    # 备注
    notes: str = ""


# ============================================================
# 公司配置表 (基于2024.1-2026.9回测结果)
# ============================================================

_COMPANY_CONFIGS: Dict[str, CompanySignalConfig] = {
    # === 表现优秀的公司 (放宽BUY条件) ===
    "1810.HK": CompanySignalConfig(
        ticker="1810.HK", name="小米集团",
        buy_score_threshold=31,  # 降低2分,更容易BUY
        pe_percentile_cap=0.85,  # 放宽估值容忍度
        notes="BUY信号T+12月+27%,历史表现最佳",
    ),
    "2252.HK": CompanySignalConfig(
        ticker="2252.HK", name="微创机器人",
        buy_score_threshold=31,
        pe_percentile_cap=0.85,
        notes="BUY信号T+12月+31%,长期表现优秀",
    ),

    # === 表现中性的公司 (保持默认) ===
    "9999.HK": CompanySignalConfig(
        ticker="9999.HK", name="网易",
        notes="BUY信号T+12月+1.4%,稳健",
    ),
    "002415.SZ": CompanySignalConfig(
        ticker="002415.SZ", name="海康威视",
        notes="BUY信号T+12月+12%,慢热型",
    ),
    "3896.HK": CompanySignalConfig(
        ticker="3896.HK", name="金山云",
        notes="BUY信号T+12月+1.6%,平淡",
    ),
    "9626.HK": CompanySignalConfig(
        ticker="9626.HK", name="B站",
        notes="BUY信号T+12月+3.9%,平庸",
    ),
    "9988.HK": CompanySignalConfig(
        ticker="9988.HK", name="阿里巴巴",
        notes="BUY信号T+12月+10.4%,先跌后涨",
    ),

    # === 表现差的公司 (收紧BUY条件) ===
    "9896.HK": CompanySignalConfig(
        ticker="9896.HK", name="名创优品",
        buy_score_threshold=36,  # 升高3分,更难BUY
        pe_percentile_cap=0.60,  # 严格估值要求
        reduce_protection_days=120,  # 更长保护期
        notes="BUY信号T+12月-43%,历史最差",
    ),
    "002352.SZ": CompanySignalConfig(
        ticker="002352.SZ", name="顺丰控股",
        buy_score_threshold=36,
        pe_percentile_cap=0.60,
        notes="BUY信号T+12月-18.5%,持续低迷",
    ),
    "600933.SS": CompanySignalConfig(
        ticker="600933.SS", name="爱柯迪",
        buy_score_threshold=35,
        pe_percentile_cap=0.65,
        notes="BUY信号T+12月-21.5%,表现差",
    ),
    "2020.HK": CompanySignalConfig(
        ticker="2020.HK", name="安踏体育",
        buy_score_threshold=35,
        pe_percentile_cap=0.70,
        notes="BUY信号T+12月-13%,买贵了",
    ),
    "3888.HK": CompanySignalConfig(
        ticker="3888.HK", name="金山软件",
        buy_score_threshold=35,
        pe_percentile_cap=0.70,
        notes="BUY信号T+12月-18.5%,逆转",
    ),
    "1361.HK": CompanySignalConfig(
        ticker="1361.HK", name="361度",
        buy_score_threshold=35,
        pe_percentile_cap=0.70,
        notes="BUY信号T+12月-10.4%,弱势",
    ),
    "LX": CompanySignalConfig(
        ticker="LX", name="乐信",
        buy_score_threshold=35,
        pe_percentile_cap=0.65,
        reduce_protection_days=120,
        notes="BUY信号高波动(+44%→-27%),需谨慎",
    ),
}


def get_company_config(ticker: str) -> CompanySignalConfig:
    """获取公司级信号配置。未配置的公司返回默认值。"""
    return _COMPANY_CONFIGS.get(ticker, CompanySignalConfig(ticker=ticker))


def list_company_configs() -> Dict[str, CompanySignalConfig]:
    """列出所有公司配置。"""
    return dict(_COMPANY_CONFIGS)
