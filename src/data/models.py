"""Data models for the YiDai investment analysis system.

8-dimension scoring framework:
  D1-D5: quantitative (profitability, health, cashflow, valuation, growth)
  D6:    quantitative (dividend quality) -- auto-computed
  D7-D8: qualitative  (ownership, strategy) -- human-scored

Grades:  A(33-40) B(26-32) C(17-25) D(9-16) F(0-8)
Signals: BUY / HOLD / WATCH / REDUCE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# 1. Company
# ---------------------------------------------------------------------------
@dataclass
class Company:
    """Basic company profile."""

    ticker: str            # e.g. "0700.HK", "600519.SS", "AAPL"
    name: str              # full company name
    market: str            # "HK", "A", or "US"
    currency: str          # "HKD", "CNY", "USD", etc.
    sector: str            # e.g. "Technology", "Consumer"
    notes: str = ""        # free-form research notes


# ---------------------------------------------------------------------------
# 2. FinancialStatement
# ---------------------------------------------------------------------------
@dataclass
class FinancialStatement:
    """Annual (or quarterly) financial snapshot.

    Numeric fields are Optional so partial data can be stored before a full
    filing is available.
    """

    ticker: str
    period: str                                        # e.g. "FY2024", "H1 2024"
    report_date: date

    # P&L
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    net_income: Optional[float] = None
    operating_income: Optional[float] = None
    ebitda: Optional[float] = None

    # Balance sheet
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    interest_bearing_debt: Optional[float] = None

    # Cash flow
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = None

    # Per-share
    shares_outstanding: Optional[float] = None
    eps: Optional[float] = None


# ---------------------------------------------------------------------------
# 3. PriceData
# ---------------------------------------------------------------------------
@dataclass
class PriceData:
    """Market price snapshot for a single day."""

    ticker: str
    date: date
    close_price: float
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None


# ---------------------------------------------------------------------------
# 4. QualitativeAssessment
# ---------------------------------------------------------------------------
@dataclass
class QualitativeAssessment:
    """Human-scored qualitative dimension (ownership or strategy).

    ``checklist`` maps checklist item labels to their status/value
    (e.g. {"founder-led": "yes", "insider-selling": "no"}).
    ``score`` is 0-5.
    """

    ticker: str
    date: date
    dimension: str                           # "ownership" or "strategy"
    checklist: Dict[str, str] = field(default_factory=dict)
    score: int = 0                           # 0-5
    notes: str = ""


# ---------------------------------------------------------------------------
# 5. ScoreResult  (auto-computed total / grade / signal)
# ---------------------------------------------------------------------------
# Grading thresholds (8 dimensions, max 40)
_GRADE_THRESHOLDS = [
    (33, "A"),
    (26, "B"),
    (17, "C"),
    (9,  "D"),
    (0,  "F"),
]


def _compute_grade(total: int) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if total >= threshold:
            return letter
    return "F"


def _compute_signal(
    total: int,
    profitability: int,
    health: int,
    cashflow: int,
    valuation: int,
    growth: int,
    dividend: int,
    ownership: int,
    strategy: int,
) -> str:
    """Determine BUY / HOLD / WATCH / REDUCE signal.

    Priority (highest first):
      1. Critical failure -> REDUCE
         health < 2  OR  cashflow < 2  OR  ownership < 1
      2. Very low total -> REDUCE (total <= 16)
      3. Any dim < 2 -> REDUCE
      4. Strong + cheap -> BUY (total >= 33 AND valuation >= 4)
      5. Adequate -> HOLD (total >= 17)
      6. Otherwise -> WATCH
    """
    scores = [profitability, health, cashflow, valuation, growth, ownership, strategy]

    # 1. Critical dimension failures
    if health < 2 or cashflow < 2 or ownership < 1:
        return "REDUCE"

    # 2. Very low total
    if total <= 16:
        return "REDUCE"

    # 3. Any single dimension critically low
    if any(s < 2 for s in scores):
        return "REDUCE"

    # 4. Strong buy signal (adjusted for 8-dim scale)
    # 审计发现: 盈利/现金流高分反预测力，健康/成长高分有预测力
    # 故增加健康和成长门槛，排除"quality trap"
    if total >= 33 and valuation >= 4 and health >= 3 and growth >= 3:
        return "BUY"

    # 5. Hold-worthy
    if total >= 17:
        return "HOLD"

    # 6. Default
    return "WATCH"


@dataclass
class ScoreResult:
    """Composite investment score across all 8 dimensions.

    ``total_score``, ``grade``, and ``signal`` are not constructor
    parameters -- they are computed automatically in ``__post_init__``
    from the eight dimension scores.

    Each dimension score is an integer in [0, 5], so total_score ranges
    from 0 to 40.
    """

    ticker: str
    date: date

    # The eight dimensions (each 0-5)
    profitability_score: int = 0   # D1 - ROE / margins
    health_score: int = 0          # D2 - leverage / liquidity
    cashflow_score: int = 0        # D3 - FCF / OCF quality
    valuation_score: int = 0       # D4 - P/E / P/B / P/S
    growth_score: int = 0          # D5 - revenue / earnings growth
    dividend_score: int = 0        # D6 - dividend quality (auto)
    ownership_score: int = 0       # D7 - qualitative (human)
    strategy_score: int = 0        # D8 - qualitative (human)

    # --- auto-computed (excluded from __init__) ---
    total_score: int = field(init=False)
    grade: str = field(init=False)
    signal: str = field(init=False)

    def __post_init__(self) -> None:
        self.total_score = (
            self.profitability_score
            + self.health_score
            + self.cashflow_score
            + self.valuation_score
            + self.growth_score
            + self.dividend_score
            + self.ownership_score
            + self.strategy_score
        )
        self.grade = _compute_grade(self.total_score)
        self.signal = _compute_signal(
            self.total_score,
            self.profitability_score,
            self.health_score,
            self.cashflow_score,
            self.valuation_score,
            self.growth_score,
            self.dividend_score,
            self.ownership_score,
            self.strategy_score,
        )
