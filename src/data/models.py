"""
Data models for the 意怠工程 (Yidai) investment analysis system.

7-dimension scoring framework:
  D1-D5: quantitative (profitability, health, cashflow, valuation, growth)
  D6-D7: qualitative  (ownership, strategy) — human-scored

Grades:  A(29-35) B(22-28) C(15-21) D(8-14) F(0-7)
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
# Grading thresholds
_GRADE_THRESHOLDS = [
    (29, "A"),
    (22, "B"),
    (15, "C"),
    (8,  "D"),
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
    ownership: int,
    strategy: int,
) -> str:
    """Determine BUY / HOLD / WATCH / REDUCE signal.

    Priority (highest first):
      1. Critical failure  → REDUCE
         health < 2  OR  cashflow < 2  OR  ownership < 1
      2. Very low total    → REDUCE   (total <= 7)
      3. Low total         → REDUCE   (total <= 14)
      4. Any dim < 2       → REDUCE
      5. Strong + cheap    → BUY      (total >= 29  AND  valuation >= 4)
      6. Adequate          → HOLD     (total >= 15)
      7. Otherwise         → WATCH
    """
    scores = [profitability, health, cashflow, valuation, growth, ownership, strategy]

    # 1. Critical dimension failures
    if health < 2 or cashflow < 2 or ownership < 1:
        return "REDUCE"

    # 2-3. Very low or low total
    if total <= 14:
        return "REDUCE"

    # 4. Any single dimension critically low
    if any(s < 2 for s in scores):
        return "REDUCE"

    # 5. Strong buy signal
    if total >= 29 and valuation >= 4:
        return "BUY"

    # 6. Hold-worthy
    if total >= 15:
        return "HOLD"

    # 7. Default
    return "WATCH"


@dataclass
class ScoreResult:
    """Composite investment score across all 7 dimensions.

    ``total_score``, ``grade``, and ``signal`` are **not** constructor
    parameters — they are computed automatically in ``__post_init__``
    from the seven dimension scores.

    Each dimension score is an integer in [0, 5], so total_score ranges
    from 0 to 35.
    """

    ticker: str
    date: date

    # The seven dimensions (each 0-5)
    profitability_score: int = 0   # D1 – ROE / margins
    health_score: int = 0          # D2 – leverage / liquidity
    cashflow_score: int = 0        # D3 – FCF / OCF quality
    valuation_score: int = 0       # D4 – P/E / P/B / P/S
    growth_score: int = 0          # D5 – revenue / earnings growth
    ownership_score: int = 0       # D6 – qualitative (human)
    strategy_score: int = 0        # D7 – qualitative (human)

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
            self.ownership_score,
            self.strategy_score,
        )
