"""Review (复盘) system for the 意怠工程 investment analysis project.

Records investment decisions, tracks holding period changes, and generates
post-mortem reviews when positions are closed.

Tables (DuckDB):
  - decision_records   : buy/sell decision snapshots
  - holding_snapshots  : periodic score snapshots during holding
  - review_records     : post-mortem reviews on position close
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import duckdb

from src.data.models import _compute_grade, _compute_signal


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DecisionRecord:
    """Records the moment of an investment decision."""

    ticker: str
    date: str                    # YYYY-MM-DD
    action: str                  # BUY or SELL
    price: float
    shares: int
    value: float                 # total transaction value

    # 7 dimension scores at decision time
    profitability_score: int
    health_score: int
    cashflow_score: int
    valuation_score: int
    growth_score: int
    ownership_score: int
    strategy_score: int
    total_score: int
    grade: str                   # A/B/C/D/F
    signal: str                  # BUY/HOLD/WATCH/REDUCE

    # Key metrics snapshot
    revenue: float = 0
    net_income: float = 0
    pe_ratio: float = 0
    gross_margin: float = 0
    roe: float = 0
    debt_ratio: float = 0

    # User thesis (filled later)
    thesis: str = ""             # Why buying/selling? (user writes this)
    risk_factors: str = ""       # What could go wrong?
    confidence: int = 3          # 1-5 user confidence level


@dataclass
class HoldingSnapshot:
    """Periodic snapshot during holding period."""

    ticker: str
    date: str
    current_price: float
    price_change_pct: float      # vs entry price

    # Current scores
    profitability_score: int
    health_score: int
    cashflow_score: int
    valuation_score: int
    growth_score: int
    ownership_score: int
    strategy_score: int
    total_score: int
    grade: str

    # Score changes vs entry
    score_delta: int             # total_score - entry_total_score
    dimension_changes: str       # human-readable: "盈利↑ 现金流↓ ..."
    alerts: str                  # deterioration warnings


@dataclass
class ReviewRecord:
    """Post-mortem review when position is closed."""

    ticker: str
    entry_date: str
    exit_date: str
    holding_days: int
    entry_price: float
    exit_price: float
    return_pct: float
    shares: int
    pnl: float                   # profit/loss in currency

    # Score comparison
    entry_total: int
    exit_total: int
    score_trajectory: str        # "improving" / "stable" / "deteriorating"

    # What happened
    what_was_right: str          # auto-generated from score analysis
    what_was_wrong: str          # auto-generated
    missed_signals: str          # warnings that appeared but were ignored

    # Framework improvement suggestions
    lessons: str                 # auto-generated lessons
    user_reflection: str = ""    # user fills this in later


# ---------------------------------------------------------------------------
# Dimension name mapping (Chinese labels for human-readable output)
# ---------------------------------------------------------------------------

_DIM_NAMES = {
    "profitability_score": "盈利",
    "health_score": "健康",
    "cashflow_score": "现金流",
    "valuation_score": "估值",
    "growth_score": "成长",
    "ownership_score": "股东",
    "strategy_score": "战略",
}

_DIM_KEYS = [
    "profitability_score",
    "health_score",
    "cashflow_score",
    "valuation_score",
    "growth_score",
    "ownership_score",
    "strategy_score",
]


# ---------------------------------------------------------------------------
# ReviewEngine
# ---------------------------------------------------------------------------

class ReviewEngine:
    """Persistent review system backed by DuckDB."""

    def __init__(self, db_path: str):
        """Initialize with DuckDB path. Creates review tables if not exist."""
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._create_tables()

    # ------------------------------------------------------------------
    # Table creation
    # ------------------------------------------------------------------

    def _create_tables(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_records (
                ticker VARCHAR,
                date VARCHAR,
                action VARCHAR,
                price DOUBLE,
                shares INTEGER,
                value DOUBLE,
                profitability_score INTEGER,
                health_score INTEGER,
                cashflow_score INTEGER,
                valuation_score INTEGER,
                growth_score INTEGER,
                ownership_score INTEGER,
                strategy_score INTEGER,
                total_score INTEGER,
                grade VARCHAR,
                signal VARCHAR,
                revenue DOUBLE DEFAULT 0,
                net_income DOUBLE DEFAULT 0,
                pe_ratio DOUBLE DEFAULT 0,
                gross_margin DOUBLE DEFAULT 0,
                roe DOUBLE DEFAULT 0,
                debt_ratio DOUBLE DEFAULT 0,
                thesis VARCHAR DEFAULT '',
                risk_factors VARCHAR DEFAULT '',
                confidence INTEGER DEFAULT 3
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS holding_snapshots (
                ticker VARCHAR,
                date VARCHAR,
                current_price DOUBLE,
                price_change_pct DOUBLE,
                profitability_score INTEGER,
                health_score INTEGER,
                cashflow_score INTEGER,
                valuation_score INTEGER,
                growth_score INTEGER,
                ownership_score INTEGER,
                strategy_score INTEGER,
                total_score INTEGER,
                grade VARCHAR,
                score_delta INTEGER,
                dimension_changes VARCHAR,
                alerts VARCHAR
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS review_records (
                ticker VARCHAR,
                entry_date VARCHAR,
                exit_date VARCHAR,
                holding_days INTEGER,
                entry_price DOUBLE,
                exit_price DOUBLE,
                return_pct DOUBLE,
                shares INTEGER,
                pnl DOUBLE,
                entry_total INTEGER,
                exit_total INTEGER,
                score_trajectory VARCHAR,
                what_was_right VARCHAR,
                what_was_wrong VARCHAR,
                missed_signals VARCHAR,
                lessons VARCHAR,
                user_reflection VARCHAR DEFAULT ''
            )
        """)

    # ------------------------------------------------------------------
    # record_decision
    # ------------------------------------------------------------------

    def record_decision(self, record: DecisionRecord) -> None:
        """Save a buy/sell decision with scores and thesis."""
        self.conn.execute("""
            INSERT INTO decision_records VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
        """, [
            record.ticker, record.date, record.action,
            record.price, record.shares, record.value,
            record.profitability_score, record.health_score,
            record.cashflow_score, record.valuation_score,
            record.growth_score, record.ownership_score,
            record.strategy_score, record.total_score,
            record.grade, record.signal,
            record.revenue, record.net_income, record.pe_ratio,
            record.gross_margin, record.roe, record.debt_ratio,
            record.thesis, record.risk_factors, record.confidence,
        ])

    # ------------------------------------------------------------------
    # take_snapshot
    # ------------------------------------------------------------------

    def take_snapshot(
        self,
        ticker: str,
        current_price: float,
        current_scores: dict,
        entry_record: DecisionRecord,
    ) -> HoldingSnapshot:
        """Take a holding period snapshot, compute changes and alerts.

        Alerts trigger when:
          - Any dimension drops by 2+ points
          - Total score drops below grade boundary
          - Signal changes from BUY to HOLD or REDUCE

        Returns the snapshot and saves it to DB.
        """
        entry_price = entry_record.price
        price_change_pct = (
            (current_price - entry_price) / entry_price * 100
            if entry_price > 0
            else 0
        )

        # Build current dimension scores
        cur = {
            k: current_scores.get(k.replace("_score", ""), 0)
            for k in _DIM_KEYS
        }
        # Allow passing keys with or without _score suffix
        for k in _DIM_KEYS:
            if k in current_scores:
                cur[k] = current_scores[k]

        total_score = sum(cur[k] for k in _DIM_KEYS)
        grade = _compute_grade(total_score)
        signal = _compute_signal(
            total_score,
            cur["profitability_score"], cur["health_score"],
            cur["cashflow_score"], cur["valuation_score"],
            cur["growth_score"], cur["ownership_score"],
            cur["strategy_score"],
        )

        # Entry scores
        entry_scores = {
            "profitability_score": entry_record.profitability_score,
            "health_score": entry_record.health_score,
            "cashflow_score": entry_record.cashflow_score,
            "valuation_score": entry_record.valuation_score,
            "growth_score": entry_record.growth_score,
            "ownership_score": entry_record.ownership_score,
            "strategy_score": entry_record.strategy_score,
        }

        score_delta = total_score - entry_record.total_score

        # Dimension changes
        changes = []
        for k in _DIM_KEYS:
            delta = cur[k] - entry_scores[k]
            if delta > 0:
                changes.append(f"{_DIM_NAMES[k]}↑")
            elif delta < 0:
                changes.append(f"{_DIM_NAMES[k]}↓")
        dimension_changes = " ".join(changes) if changes else "无变化"

        # Alerts
        alerts = []
        for k in _DIM_KEYS:
            delta = cur[k] - entry_scores[k]
            if delta <= -2:
                alerts.append(
                    f"⚠️ {_DIM_NAMES[k]}大幅下降 (从{entry_scores[k]}降至{cur[k]})"
                )

        # Grade boundary check
        entry_grade = entry_record.grade
        grade_order = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        if grade_order.get(grade, 0) < grade_order.get(entry_grade, 0):
            alerts.append(
                f"⚠️ 评级从{entry_grade}降至{grade}"
            )

        # Signal change check
        entry_signal = entry_record.signal
        if entry_signal == "BUY" and signal in ("HOLD", "REDUCE"):
            alerts.append(
                f"⚠️ 信号从{entry_signal}变为{signal}"
            )

        alerts_str = "\n".join(alerts) if alerts else ""

        today = date.today().isoformat()

        snapshot = HoldingSnapshot(
            ticker=ticker,
            date=today,
            current_price=current_price,
            price_change_pct=round(price_change_pct, 2),
            profitability_score=cur["profitability_score"],
            health_score=cur["health_score"],
            cashflow_score=cur["cashflow_score"],
            valuation_score=cur["valuation_score"],
            growth_score=cur["growth_score"],
            ownership_score=cur["ownership_score"],
            strategy_score=cur["strategy_score"],
            total_score=total_score,
            grade=grade,
            score_delta=score_delta,
            dimension_changes=dimension_changes,
            alerts=alerts_str,
        )

        # Save to DB
        self.conn.execute("""
            INSERT INTO holding_snapshots VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, [
            snapshot.ticker, snapshot.date, snapshot.current_price,
            snapshot.price_change_pct,
            snapshot.profitability_score, snapshot.health_score,
            snapshot.cashflow_score, snapshot.valuation_score,
            snapshot.growth_score, snapshot.ownership_score,
            snapshot.strategy_score, snapshot.total_score, snapshot.grade,
            snapshot.score_delta, snapshot.dimension_changes, snapshot.alerts,
        ])

        return snapshot

    # ------------------------------------------------------------------
    # generate_review
    # ------------------------------------------------------------------

    def generate_review(
        self,
        ticker: str,
        exit_date: str,
        exit_price: float,
        exit_scores: dict,
    ) -> ReviewRecord:
        """Generate post-mortem review when closing a position.

        Reads all decision records and snapshots for this ticker.
        Computes what_was_right, what_was_wrong, lessons.
        Returns and saves the review.
        """
        # Get the BUY decision (entry)
        entry_rows = self.conn.execute(
            "SELECT * FROM decision_records WHERE ticker = ? AND action = 'BUY' ORDER BY date LIMIT 1",
            [ticker],
        ).fetchall()
        if not entry_rows:
            raise ValueError(f"No BUY decision found for {ticker}")

        entry = entry_rows[0]
        # columns: ticker, date, action, price, shares, value,
        #   profitability_score, health_score, cashflow_score, valuation_score,
        #   growth_score, ownership_score, strategy_score, total_score, grade, signal,
        #   revenue, net_income, pe_ratio, gross_margin, roe, debt_ratio,
        #   thesis, risk_factors, confidence
        entry_date = entry[1]
        entry_price = entry[3]
        entry_shares = entry[4]
        entry_total = entry[13]
        entry_signal = entry[15]

        entry_scores = {
            "profitability_score": entry[6],
            "health_score": entry[7],
            "cashflow_score": entry[8],
            "valuation_score": entry[9],
            "growth_score": entry[10],
            "ownership_score": entry[11],
            "strategy_score": entry[12],
        }

        # Compute exit scores
        exit_dim = {}
        for k in _DIM_KEYS:
            short = k.replace("_score", "")
            exit_dim[k] = exit_scores.get(k, exit_scores.get(short, 0))

        exit_total = sum(exit_dim[k] for k in _DIM_KEYS)
        exit_grade = _compute_grade(exit_total)

        # P&L
        return_pct = (
            (exit_price - entry_price) / entry_price * 100
            if entry_price > 0
            else 0
        )
        pnl = (exit_price - entry_price) * entry_shares

        # Holding days
        d_entry = datetime.strptime(entry_date, "%Y-%m-%d").date()
        d_exit = datetime.strptime(exit_date, "%Y-%m-%d").date()
        holding_days = (d_exit - d_entry).days

        # Score trajectory
        score_diff = exit_total - entry_total
        if score_diff >= 3:
            score_trajectory = "improving"
        elif score_diff <= -3:
            score_trajectory = "deteriorating"
        else:
            score_trajectory = "stable"

        # --- what_was_right ---
        right_items = []
        for k in _DIM_KEYS:
            if exit_dim[k] >= 4:
                right_items.append(f"{_DIM_NAMES[k]}保持强势({exit_dim[k]}/5)")
            elif exit_dim[k] > entry_scores[k]:
                right_items.append(
                    f"{_DIM_NAMES[k]}改善({entry_scores[k]}→{exit_dim[k]})"
                )
        what_was_right = "; ".join(right_items) if right_items else "无明显亮点"

        # --- what_was_wrong ---
        wrong_items = []
        for k in _DIM_KEYS:
            delta = exit_dim[k] - entry_scores[k]
            if delta <= -2:
                wrong_items.append(
                    f"{_DIM_NAMES[k]}大幅下降({entry_scores[k]}→{exit_dim[k]})"
                )
        what_was_wrong = "; ".join(wrong_items) if wrong_items else "无明显恶化"

        # --- missed_signals ---
        snapshots = self.conn.execute(
            "SELECT * FROM holding_snapshots WHERE ticker = ? ORDER BY date",
            [ticker],
        ).fetchall()

        missed = []
        for snap in snapshots:
            # snap[15] = alerts
            if snap[15] and snap[15].strip():
                missed.append(f"{snap[1]}: {snap[15].strip()}")
        missed_signals = "\n".join(missed) if missed else "无警告信号"

        # --- lessons ---
        lessons = self._generate_lessons(
            return_pct, entry_scores, exit_dim, entry_total, exit_total,
        )

        review = ReviewRecord(
            ticker=ticker,
            entry_date=entry_date,
            exit_date=exit_date,
            holding_days=holding_days,
            entry_price=entry_price,
            exit_price=exit_price,
            return_pct=round(return_pct, 2),
            shares=entry_shares,
            pnl=round(pnl, 2),
            entry_total=entry_total,
            exit_total=exit_total,
            score_trajectory=score_trajectory,
            what_was_right=what_was_right,
            what_was_wrong=what_was_wrong,
            missed_signals=missed_signals,
            lessons=lessons,
        )

        # Save to DB
        self.conn.execute("""
            INSERT INTO review_records VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, [
            review.ticker, review.entry_date, review.exit_date,
            review.holding_days, review.entry_price, review.exit_price,
            review.return_pct, review.shares, review.pnl,
            review.entry_total, review.exit_total, review.score_trajectory,
            review.what_was_right, review.what_was_wrong,
            review.missed_signals, review.lessons, review.user_reflection,
        ])

        return review

    def _generate_lessons(
        self,
        return_pct: float,
        entry_scores: dict,
        exit_scores: dict,
        entry_total: int,
        exit_total: int,
    ) -> str:
        """Auto-generate lessons based on pattern matching."""
        lessons = []

        is_loss = return_pct < 0
        cf_deteriorated = (
            exit_scores.get("cashflow_score", 0)
            < entry_scores.get("cashflow_score", 0)
        )
        growth_deteriorated = (
            exit_scores.get("growth_score", 0)
            < entry_scores.get("growth_score", 0)
        )

        if is_loss and cf_deteriorated:
            lessons.append("📊 现金流恶化是先行指标，需加强现金流监控")

        if is_loss and growth_deteriorated:
            lessons.append("📈 成长放缓是领先指标，需关注增长趋势变化")

        if not is_loss and exit_total >= entry_total:
            lessons.append("💪 坚持投资论点得到回报，基本面改善验证了买入逻辑")

        if entry_scores.get("valuation_score", 5) <= 2:
            lessons.append("💰 估值纪律不足，追高买入风险大")

        # Check for high entry valuation
        if entry_scores.get("valuation_score", 0) <= 2 and is_loss:
            lessons.append("🔍 低估值是安全边际，高估值买入需更谨慎")

        if not lessons:
            if is_loss:
                lessons.append("📝 回顾投资论点，识别关键假设失误")
            else:
                lessons.append("✅ 操作得当，继续保持纪律性")

        return "\n".join(lessons)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_decision_history(self, ticker: str = None) -> List[dict]:
        """Get all decisions, optionally filtered by ticker."""
        columns = [
            "ticker", "date", "action", "price", "shares", "value",
            "profitability_score", "health_score", "cashflow_score",
            "valuation_score", "growth_score", "ownership_score",
            "strategy_score", "total_score", "grade", "signal",
            "revenue", "net_income", "pe_ratio", "gross_margin",
            "roe", "debt_ratio", "thesis", "risk_factors", "confidence",
        ]

        if ticker:
            rows = self.conn.execute(
                "SELECT * FROM decision_records WHERE ticker = ? ORDER BY date",
                [ticker],
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM decision_records ORDER BY ticker, date"
            ).fetchall()

        return [dict(zip(columns, row)) for row in rows]

    def get_holding_snapshots(self, ticker: str) -> List[dict]:
        """Get all snapshots for a ticker."""
        columns = [
            "ticker", "date", "current_price", "price_change_pct",
            "profitability_score", "health_score", "cashflow_score",
            "valuation_score", "growth_score", "ownership_score",
            "strategy_score", "total_score", "grade", "score_delta",
            "dimension_changes", "alerts",
        ]
        rows = self.conn.execute(
            "SELECT * FROM holding_snapshots WHERE ticker = ? ORDER BY date",
            [ticker],
        ).fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def get_reviews(self, ticker: str = None) -> List[dict]:
        """Get all reviews, optionally filtered by ticker."""
        columns = [
            "ticker", "entry_date", "exit_date", "holding_days",
            "entry_price", "exit_price", "return_pct", "shares", "pnl",
            "entry_total", "exit_total", "score_trajectory",
            "what_was_right", "what_was_wrong", "missed_signals",
            "lessons", "user_reflection",
        ]

        if ticker:
            rows = self.conn.execute(
                "SELECT * FROM review_records WHERE ticker = ? ORDER BY exit_date",
                [ticker],
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM review_records ORDER BY ticker, exit_date"
            ).fetchall()

        return [dict(zip(columns, row)) for row in rows]

    # ------------------------------------------------------------------
    # generate_weekly_check
    # ------------------------------------------------------------------

    def generate_weekly_check(
        self,
        ticker: str,
        current_price: float,
        current_scores: dict,
    ) -> str:
        """Generate a weekly holding check message.

        Compares current scores vs entry, identifies trends.
        Returns markdown text suitable for inclusion in weekly report.
        """
        # Get the entry decision
        entry_rows = self.conn.execute(
            "SELECT * FROM decision_records WHERE ticker = ? AND action = 'BUY' ORDER BY date LIMIT 1",
            [ticker],
        ).fetchall()
        if not entry_rows:
            return f"## {ticker} 持仓检查\n\n⚠️ 未找到买入记录"

        entry = entry_rows[0]
        entry_price = entry[3]
        entry_total = entry[13]
        entry_signal = entry[15]
        entry_date = entry[1]

        entry_scores = {
            "profitability_score": entry[6],
            "health_score": entry[7],
            "cashflow_score": entry[8],
            "valuation_score": entry[9],
            "growth_score": entry[10],
            "ownership_score": entry[11],
            "strategy_score": entry[12],
        }

        # Compute current scores
        cur = {}
        for k in _DIM_KEYS:
            short = k.replace("_score", "")
            cur[k] = current_scores.get(k, current_scores.get(short, 0))

        total_score = sum(cur[k] for k in _DIM_KEYS)
        grade = _compute_grade(total_score)
        signal = _compute_signal(
            total_score,
            cur["profitability_score"], cur["health_score"],
            cur["cashflow_score"], cur["valuation_score"],
            cur["growth_score"], cur["ownership_score"],
            cur["strategy_score"],
        )

        # Price change
        price_change_pct = (
            (current_price - entry_price) / entry_price * 100
            if entry_price > 0
            else 0
        )

        # Build markdown
        lines = [
            f"## {ticker} 周度持仓检查",
            "",
            f"**买入日期**: {entry_date}  ",
            f"**买入价格**: {entry_price:.2f}  ",
            f"**当前价格**: {current_price:.2f} ({price_change_pct:+.1f}%)  ",
            "",
            "### 评分对比",
            "",
            "| 维度 | 买入时 | 当前 | 变化 |",
            "|------|--------|------|------|",
        ]

        for k in _DIM_KEYS:
            name = _DIM_NAMES[k]
            old = entry_scores[k]
            new = cur[k]
            delta = new - old
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            lines.append(f"| {name} | {old} | {new} | {delta:+d} {arrow} |")

        score_delta = total_score - entry_total
        lines.append(
            f"| **总计** | **{entry_total}** | **{total_score}** | "
            f"**{score_delta:+d}** |"
        )
        lines.append("")
        lines.append(f"**评级**: {grade}  **信号**: {signal}  ")
        lines.append(f"**买入时信号**: {entry_signal}  ")
        lines.append("")

        # Alerts
        alerts = []
        for k in _DIM_KEYS:
            delta = cur[k] - entry_scores[k]
            if delta <= -2:
                alerts.append(
                    f"- ⚠️ {_DIM_NAMES[k]}大幅下降 "
                    f"({entry_scores[k]} → {cur[k]})"
                )

        if alerts:
            lines.append("### ⚠️ 警告信号")
            lines.extend(alerts)
            lines.append("")

        # Strong dimensions
        strong = [
            f"{_DIM_NAMES[k]}" for k in _DIM_KEYS if cur[k] >= 4
        ]
        if strong:
            lines.append("### 💪 强势维度")
            lines.append(", ".join(strong))
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
