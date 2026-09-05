"""Data models for the YiDai investment analysis system.

8-dimension scoring framework:
  D1-D5: quantitative (profitability, health, cashflow, valuation, growth)
  D6:    quantitative (dividend quality) -- auto-computed
  D7-D8: qualitative  (ownership, strategy) -- human-scored

Grades:  A(33-40) B(26-32) C(17-25) D(9-16) F(0-8)
Signals: BUY / HOLD / WATCH / REDUCE

Dimension weights (from multi-window accuracy audit 2026-08-29):
  有预测力: 健康(+0.50) 估值(+0.50) 股东(+0.50) 战略(+0.50)
  弱预测力: 成长(+0.13)
  反预测力: 盈利(-0.35) 现金流(-0.42)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Dimension weights — based on multi-window accuracy audit (2026-08-29)
# Each dimension score (0-5) is multiplied by its weight for signal decisions.
# Raw total_score (unweighted) is still used for grade calculation.
# ---------------------------------------------------------------------------
DIMENSION_WEIGHTS: Dict[str, float] = {
    "profitability": 0.5,   # 反预测力(-0.35), 降权
    "health":        1.5,   # 强预测力(+0.50), 加权
    "cashflow":      0.5,   # 反预测力(-0.42), 降权
    "valuation":     1.5,   # 强预测力(+0.50), 加权
    "growth":        1.0,   # 弱预测力(+0.13), 维持
    "dividend":      0.8,   # 样本不足, 轻微降权
    "ownership":     1.2,   # 强预测力(+0.50), 加权
    "strategy":      1.2,   # 强预测力(+0.50), 加权
}


def _compute_weighted_total(
    profitability: int, health: int, cashflow: int,
    valuation: int, growth: int, dividend: int,
    ownership: int, strategy: int,
) -> float:
    """Compute weighted total score for signal decisions.

    Returns a float. Max possible = 5 * sum(weights) ≈ 41.0
    """
    scores = {
        "profitability": profitability, "health": health,
        "cashflow": cashflow, "valuation": valuation,
        "growth": growth, "dividend": dividend,
        "ownership": ownership, "strategy": strategy,
    }
    return sum(scores[k] * DIMENSION_WEIGHTS[k] for k in DIMENSION_WEIGHTS)


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
    weighted_total: Optional[float] = None,
    qualitative_confirmed: bool = True,
    pe_percentile: Optional[float] = None,
    prev_signal: Optional[str] = None,
    prev_signal_date: Optional[str] = None,
    eval_date: Optional[str] = None,
    pe_cap: float = 0.80,
    buy_score_delta: int = 0,
) -> str:
    """Determine BUY / HOLD / WATCH / REDUCE signal.

    Priority (highest first):
      1. Critical failure -> REDUCE
         health < 2  OR  cashflow < 2  OR  ownership < 1
      2. Very low total -> REDUCE (total <= 16)
      3. Any quant dim < 2 -> REDUCE (excludes ownership/strategy)
      4. Strong + cheap + confirmed -> BUY (with valuation guard)
      5. Adequate -> HOLD (total >= 17)
      6. Otherwise -> WATCH

    weighted_total: if provided, uses dimension-weighted score for BUY threshold.
    qualitative_confirmed: if False, blocks BUY (D7/D8 not manually scored).
    pe_percentile: if provided, blocks BUY when PE > pe_cap percentile.
    pe_cap: PE percentile cap for BUY (default 0.80, adjusted by regime).
    buy_score_delta: regime-based adjustment to BUY threshold (default 0).
    prev_signal: previous signal type for holding protection.
    prev_signal_date: date of previous signal (ISO string).
    eval_date: current evaluation date (ISO string).
    """
    # Quantitative dims only for critical check (exclude ownership/strategy)
    # dividend=0 means "no data", not "bad" — exclude from critical check
    quant_scores = [profitability, health, cashflow, valuation, growth]
    if dividend > 0:
        quant_scores.append(dividend)

    # 1. Critical dimension failures (quantitative only)
    if health < 2 or cashflow < 2:
        return "REDUCE"

    # 2. Very low total
    if total <= 16:
        return "REDUCE"

    # 3. Any quantitative dimension critically low
    if any(s < 2 for s in quant_scores):
        return "REDUCE"

    # 4. Strong buy signal — requires qualitative confirmation
    # 审计发现: 健康/估值/股东/战略有预测力, 盈利/现金流反预测力
    check_total = weighted_total if weighted_total is not None else total
    # Apply regime-based BUY threshold adjustment
    effective_buy_threshold = 33 + buy_score_delta
    if (check_total >= effective_buy_threshold and valuation >= 4 and health >= 3 and growth >= 3
            and qualitative_confirmed):

        # --- Improvement 1: Valuation guard ---
        # Block BUY if PE is at expensive valuations
        # pe_cap is regime-adjusted (bear: 0.70, neutral: 0.80, bull: 0.85)
        if pe_percentile is not None and pe_percentile > pe_cap:
            return "HOLD"  # Downgrade BUY to HOLD when expensive

        # --- Improvement 2: REDUCE holding protection ---
        # After REDUCE signal, block BUY for 3 months to avoid whipsawing
        if prev_signal == "REDUCE" and prev_signal_date and eval_date:
            try:
                from datetime import date as _date
                psd = _date.fromisoformat(prev_signal_date)
                ed = _date.fromisoformat(eval_date)
                days_since_reduce = (ed - psd).days
                if days_since_reduce < 90:  # 3 months = ~90 days
                    return "HOLD"  # Still in protection period
            except (ValueError, TypeError):
                pass  # Date parsing failed, skip protection

        return "BUY"

    # 4b. Cautious re-entry after REDUCE protection period
    # After 90-day protection expires, allow BUY at slightly lower threshold
    # This captures mean-reversion opportunities with proper confirmation
    if prev_signal == "REDUCE" and prev_signal_date and eval_date:
        try:
            from datetime import date as _date2
            psd2 = _date2.fromisoformat(prev_signal_date)
            ed2 = _date2.fromisoformat(eval_date)
            days_since_reduce2 = (ed2 - psd2).days
            # After protection period (90d) but within 180d: cautious re-entry
            if 90 <= days_since_reduce2 <= 180:
                # Require strong fundamentals but relaxed total score
                if (check_total >= effective_buy_threshold - 2
                        and valuation >= 3 and health >= 3 and growth >= 3
                        and qualitative_confirmed):
                    # Still apply PE guard
                    if pe_percentile is not None and pe_percentile > pe_cap:
                        return "HOLD"
                    return "BUY"
        except (ValueError, TypeError):
            pass

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
    weighted_total: float = field(init=False)
    grade: str = field(init=False)
    signal: str = field(init=False)

    # --- qualitative confirmation flag ---
    qualitative_confirmed: bool = True

    # --- improvement fields (optional) ---
    pe_percentile: Optional[float] = None
    prev_signal: Optional[str] = None
    prev_signal_date: Optional[str] = None
    eval_date: Optional[str] = None
    pe_cap: float = 0.80
    buy_score_delta: int = 0

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
        self.weighted_total = _compute_weighted_total(
            self.profitability_score, self.health_score,
            self.cashflow_score, self.valuation_score,
            self.growth_score, self.dividend_score,
            self.ownership_score, self.strategy_score,
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
            weighted_total=self.weighted_total,
            qualitative_confirmed=self.qualitative_confirmed,
            pe_percentile=self.pe_percentile,
            prev_signal=self.prev_signal,
            prev_signal_date=self.prev_signal_date,
            eval_date=self.eval_date,
            pe_cap=self.pe_cap,
            buy_score_delta=self.buy_score_delta,
        )
