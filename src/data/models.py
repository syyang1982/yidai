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

import json
import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Dimension weights — based on multi-window accuracy audit (2026-08-29)
# Each dimension score (0-5) is multiplied by its weight for signal decisions.
# Raw total_score (unweighted) is still used for grade calculation.
#
# 闭环反馈 (2026-09-22): 权重可被 config/feedback_weights.json 覆盖。
# 复盘结论 (维度预测力) 经 src/strategy/feedback.py 计算后写入该文件，
# 从而形成 分析 → 记录 → 复盘 → 反馈回分析 的完整闭环。
# 未生成覆盖文件时行为与之前完全一致（默认权重）。
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

# 复盘回灌的覆盖文件位置（不存在则用 DIMENSION_WEIGHTS）
FEEDBACK_WEIGHTS_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "feedback_weights.json"
))


@lru_cache(maxsize=1)
def load_dimension_weights() -> Dict[str, float]:
    """Return effective dimension weights.

    优先读 config/feedback_weights.json（由 manage.py feedback --apply 生成），
    文件缺失或格式非法时回退到内置 DIMENSION_WEIGHTS，绝不抛异常。
    只接受 8 个已知维度的完整覆盖，缺键/多键一律拒绝并回退。
    """
    try:
        with open(FEEDBACK_WEIGHTS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        weights = raw.get("weights", raw) if isinstance(raw, dict) else None
        if not isinstance(weights, dict):
            return dict(DIMENSION_WEIGHTS)
        if set(weights) != set(DIMENSION_WEIGHTS):
            return dict(DIMENSION_WEIGHTS)
        out = {k: float(weights[k]) for k in DIMENSION_WEIGHTS}
        if any(v <= 0 for v in out.values()):
            return dict(DIMENSION_WEIGHTS)
        return out
    except Exception:
        return dict(DIMENSION_WEIGHTS)


def reset_dimension_weights_cache() -> None:
    """Clear the cached weights (for tests / after writing an override)."""
    load_dimension_weights.cache_clear()


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
    weights = load_dimension_weights()
    return sum(scores[k] * weights[k] for k in weights)


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


def _compute_grade(total: float) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if total >= threshold:
            return letter
    return "F"


# ---------------------------------------------------------------------------
# 实评维度归一化 (2026-09-22, W7.10)
# ---------------------------------------------------------------------------
# 分档 (_GRADE_THRESHOLDS) 与信号阈值都是按「8 维 / 满分 40」校准的，
# 但某些维度可能没有数据（最典型：不发股息的公司 D6，以及 review/backtest
# 这类只有 7 个维度字段的记录）。直接拿 7 维满分 35 的 raw total 去比 33 的
# BUY 线，等价于要求 35 分里拿 94% —— BUY 被系统性压制。
#
# 因此：分档与信号一律用「归一到 8 维 40 分制」的分数，
# raw total 仍保留用于展示与历史对比。
# ---------------------------------------------------------------------------
DIMENSION_KEYS: tuple = (
    "profitability", "health", "cashflow", "valuation",
    "growth", "dividend", "ownership", "strategy",
)

#: 无分红数据时 D6 不计入分母（与 _compute_signal 中「dividend=0 表示无数据」同口径）
DIMENSIONS_EXCEPT_DIVIDEND: tuple = tuple(k for k in DIMENSION_KEYS if k != "dividend")

_MAX_PER_DIM = 5
_FULL_SCALE = _MAX_PER_DIM * len(DIMENSION_KEYS)   # 40


def normalize_total(raw_total: float, scored_dimensions=None) -> float:
    """把「只实评了 n 个维度」的原始总分换算到 8 维 40 分制。

    ``scored_dimensions=None`` 表示 8 个维度全部实评 —— 此时原样返回，
    对既有全量评分零行为变化。
    """
    n = len(DIMENSION_KEYS) if scored_dimensions is None else len(scored_dimensions)
    if n <= 0:
        return 0.0
    if n >= len(DIMENSION_KEYS):
        return float(raw_total)
    return float(raw_total) * _FULL_SCALE / (_MAX_PER_DIM * n)


def _compute_signal(
    total: float,
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
    data_complete: bool = True,
) -> str:
    """Determine BUY / HOLD / WATCH / REDUCE signal.

    Priority (highest first):
      1. Critical failure -> REDUCE
         health < 2  OR  cashflow < 2  OR  ownership < 1
      2. Very low total -> REDUCE (total <= 16)
      3. Any quant dim < 2 -> REDUCE (excludes ownership/strategy)
      4. Strong + cheap + confirmed + complete data -> BUY (with valuation guard)
      5. Adequate -> HOLD (total >= 17)
      6. Otherwise -> WATCH

    weighted_total: if provided, uses dimension-weighted score for BUY threshold.
    qualitative_confirmed: if False, blocks BUY (D7/D8 not manually scored).
    data_complete: if False, blocks BUY (health/cashflow inputs missing).
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
            and qualitative_confirmed and data_complete):

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
                        and qualitative_confirmed and data_complete):
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
    #: 实评维度个数 + 归一到 8 维 40 分制的分数（分档/信号用它，不用 raw total）
    scored_count: int = field(init=False)
    normalized_total: float = field(init=False)
    grade: str = field(init=False)
    signal: str = field(init=False)

    # --- qualitative confirmation flag ---
    qualitative_confirmed: bool = True
    # --- missing health/cashflow inputs must not silently score as 3 and fire BUY ---
    data_complete: bool = True
    missing_fields: list = field(default_factory=list)
    #: 实际评了哪几个维度（DIMENSION_KEYS 的子集）。
    #: None = 8 维全部实评（既有全量评分零行为变化）。
    #: 无分红数据时传 DIMENSIONS_EXCEPT_DIVIDEND，D6 不计入归一化分母。
    scored_dimensions: Optional[tuple] = None

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
        self.scored_count = (
            len(DIMENSION_KEYS) if self.scored_dimensions is None
            else len(self.scored_dimensions)
        )
        # 分档 / 信号一律用归一到 8 维 40 分制的分数（理由见 normalize_total）
        self.normalized_total = normalize_total(self.total_score, self.scored_dimensions)
        self.weighted_total = _compute_weighted_total(
            self.profitability_score, self.health_score,
            self.cashflow_score, self.valuation_score,
            self.growth_score, self.dividend_score,
            self.ownership_score, self.strategy_score,
        )
        # 加权分同样归一到「全维度」口径（满分 sum(weights)*5 ≈ 41），
        # 否则缺维度的公司照样够不到 BUY 门槛。
        if self.scored_dimensions is not None and self.scored_count < len(DIMENSION_KEYS):
            _w_scored = sum(
                DIMENSION_WEIGHTS[k] for k in self.scored_dimensions
                if k in DIMENSION_WEIGHTS
            )
            _w_all = sum(DIMENSION_WEIGHTS.values())
            if _w_scored > 0:
                self.weighted_total = self.weighted_total * _w_all / _w_scored
        self.grade = _compute_grade(self.normalized_total)
        self.signal = _compute_signal(
            self.normalized_total,
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
            data_complete=self.data_complete,
        )
