"""Tests for the review (复盘) system.

Covers:
  - DecisionRecord: creation with all fields, defaults
  - HoldingSnapshot: score_delta computation, dimension_changes text
  - ReviewRecord: return_pct, pnl computation
  - ReviewEngine: full lifecycle, queries, edge cases
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from strategy.review import (
    DecisionRecord,
    HoldingSnapshot,
    ReviewRecord,
    ReviewEngine,
    _DIM_KEYS,
    _DIM_NAMES,
)


# =========================================================================
# Fixtures
# =========================================================================

def _make_decision(
    ticker="TEST",
    date="2024-01-15",
    action="BUY",
    price=100.0,
    shares=1000,
    value=100000.0,
    profitability=4,
    health=4,
    cashflow=4,
    valuation=4,
    growth=4,
    ownership=4,
    strategy=4,
    signal="BUY",
    **kwargs,
) -> DecisionRecord:
    """Helper to create a DecisionRecord with sensible defaults."""
    total = profitability + health + cashflow + valuation + growth + ownership + strategy
    from src.data.models import _compute_grade
    grade = _compute_grade(total)
    return DecisionRecord(
        ticker=ticker,
        date=date,
        action=action,
        price=price,
        shares=shares,
        value=value,
        profitability_score=profitability,
        health_score=health,
        cashflow_score=cashflow,
        valuation_score=valuation,
        growth_score=growth,
        ownership_score=ownership,
        strategy_score=strategy,
        total_score=total,
        grade=grade,
        signal=signal,
        **kwargs,
    )


def _scores(profitability=4, health=4, cashflow=4, valuation=4,
            growth=4, ownership=4, strategy=4) -> dict:
    """Build a scores dict using the _score suffix keys."""
    return {
        "profitability_score": profitability,
        "health_score": health,
        "cashflow_score": cashflow,
        "valuation_score": valuation,
        "growth_score": growth,
        "ownership_score": ownership,
        "strategy_score": strategy,
    }


@pytest.fixture
def engine(tmp_path):
    """Create a ReviewEngine with a temporary DuckDB."""
    db = str(tmp_path / "test_review.duckdb")
    eng = ReviewEngine(db)
    yield eng
    eng.close()


# =========================================================================
# TestDecisionRecord
# =========================================================================

class TestDecisionRecord:
    def test_creation_all_fields(self):
        rec = DecisionRecord(
            ticker="0700.HK",
            date="2024-06-01",
            action="BUY",
            price=350.0,
            shares=200,
            value=70000.0,
            profitability_score=5,
            health_score=4,
            cashflow_score=3,
            valuation_score=2,
            growth_score=4,
            ownership_score=3,
            strategy_score=4,
            total_score=25,
            grade="B",
            signal="HOLD",
            revenue=1000000,
            net_income=200000,
            pe_ratio=15.0,
            gross_margin=0.6,
            roe=0.25,
            debt_ratio=0.3,
            thesis="Growth play",
            risk_factors="Regulatory",
            confidence=4,
        )
        assert rec.ticker == "0700.HK"
        assert rec.action == "BUY"
        assert rec.total_score == 25
        assert rec.grade == "B"
        assert rec.signal == "HOLD"
        assert rec.revenue == 1000000
        assert rec.thesis == "Growth play"
        assert rec.confidence == 4

    def test_defaults(self):
        rec = DecisionRecord(
            ticker="TEST",
            date="2024-01-01",
            action="BUY",
            price=10.0,
            shares=100,
            value=1000.0,
            profitability_score=3,
            health_score=3,
            cashflow_score=3,
            valuation_score=3,
            growth_score=3,
            ownership_score=3,
            strategy_score=3,
            total_score=21,
            grade="C",
            signal="HOLD",
        )
        assert rec.revenue == 0
        assert rec.net_income == 0
        assert rec.pe_ratio == 0
        assert rec.gross_margin == 0
        assert rec.roe == 0
        assert rec.debt_ratio == 0
        assert rec.thesis == ""
        assert rec.risk_factors == ""
        assert rec.confidence == 3


# =========================================================================
# TestHoldingSnapshot
# =========================================================================

class TestHoldingSnapshot:
    def test_score_delta(self):
        entry = _make_decision(price=100.0, profitability=4, health=4,
                               cashflow=4, valuation=4, growth=4,
                               ownership=4, strategy=4)  # total=28
        snap = HoldingSnapshot(
            ticker="TEST",
            date="2024-06-01",
            current_price=110.0,
            price_change_pct=10.0,
            profitability_score=4,
            health_score=3,
            cashflow_score=4,
            valuation_score=3,
            growth_score=4,
            ownership_score=4,
            strategy_score=4,
            total_score=26,
            grade="B",
            score_delta=-2,
            dimension_changes="健康↓ 估值↓",
            alerts="",
        )
        assert snap.score_delta == -2
        assert snap.total_score == 26

    def test_dimension_changes_text(self):
        snap = HoldingSnapshot(
            ticker="TEST",
            date="2024-06-01",
            current_price=110.0,
            price_change_pct=10.0,
            profitability_score=5,
            health_score=3,
            cashflow_score=4,
            valuation_score=4,
            growth_score=4,
            ownership_score=4,
            strategy_score=4,
            total_score=28,
            grade="B",
            score_delta=0,
            dimension_changes="盈利↑ 健康↓",
            alerts="",
        )
        assert "盈利↑" in snap.dimension_changes
        assert "健康↓" in snap.dimension_changes

    def test_computed_via_engine(self, engine):
        """Test that take_snapshot computes score_delta and dimension_changes correctly."""
        entry = _make_decision(
            price=50.0, profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        engine.record_decision(entry)

        new_scores = _scores(profitability=5, health=2, cashflow=4,
                             valuation=4, growth=4, ownership=4, strategy=4)
        snap = engine.take_snapshot("TEST", 55.0, new_scores, entry)

        # score_delta = (5+2+4+4+4+4+4) - 28 = 27 - 28 = -1
        assert snap.score_delta == -1
        assert "盈利↑" in snap.dimension_changes
        assert "健康↓" in snap.dimension_changes
        assert snap.price_change_pct == pytest.approx(10.0)


# =========================================================================
# TestReviewRecord
# =========================================================================

class TestReviewRecord:
    def test_return_pct_and_pnl(self):
        review = ReviewRecord(
            ticker="TEST",
            entry_date="2024-01-01",
            exit_date="2024-07-01",
            holding_days=182,
            entry_price=100.0,
            exit_price=120.0,
            return_pct=20.0,
            shares=1000,
            pnl=20000.0,
            entry_total=28,
            exit_total=30,
            score_trajectory="improving",
            what_was_right="",
            what_was_wrong="",
            missed_signals="",
            lessons="",
        )
        assert review.return_pct == 20.0
        assert review.pnl == 20000.0

    def test_loss_scenario(self):
        review = ReviewRecord(
            ticker="TEST",
            entry_date="2024-01-01",
            exit_date="2024-04-01",
            holding_days=91,
            entry_price=100.0,
            exit_price=80.0,
            return_pct=-20.0,
            shares=500,
            pnl=-10000.0,
            entry_total=28,
            exit_total=18,
            score_trajectory="deteriorating",
            what_was_right="",
            what_was_wrong="",
            missed_signals="",
            lessons="",
        )
        assert review.return_pct == -20.0
        assert review.pnl == -10000.0
        assert review.score_trajectory == "deteriorating"


# =========================================================================
# TestReviewEngine — record_decision + get_decision_history
# =========================================================================

class TestRecordDecision:
    def test_save_and_retrieve(self, engine):
        rec = _make_decision(ticker="AAPL", date="2024-03-15")
        engine.record_decision(rec)

        history = engine.get_decision_history("AAPL")
        assert len(history) == 1
        assert history[0]["ticker"] == "AAPL"
        assert history[0]["action"] == "BUY"
        assert history[0]["price"] == 100.0
        assert history[0]["shares"] == 1000
        assert history[0]["total_score"] == 28
        assert history[0]["grade"] == "B"

    def test_multiple_decisions(self, engine):
        engine.record_decision(_make_decision(ticker="AAPL", date="2024-01-01"))
        engine.record_decision(_make_decision(ticker="AAPL", date="2024-06-01",
                                              action="SELL"))
        engine.record_decision(_make_decision(ticker="MSFT", date="2024-02-01"))

        # All decisions
        all_dec = engine.get_decision_history()
        assert len(all_dec) == 3

        # Filter by ticker
        aapl = engine.get_decision_history("AAPL")
        assert len(aapl) == 2

        msft = engine.get_decision_history("MSFT")
        assert len(msft) == 1

    def test_decision_with_custom_metrics(self, engine):
        rec = _make_decision(
            revenue=500000, net_income=100000, pe_ratio=12.5,
            gross_margin=0.45, roe=0.18, debt_ratio=0.35,
            thesis="Undervalued", risk_factors="Competition", confidence=4,
        )
        engine.record_decision(rec)
        history = engine.get_decision_history("TEST")
        assert history[0]["revenue"] == 500000
        assert history[0]["thesis"] == "Undervalued"
        assert history[0]["confidence"] == 4


# =========================================================================
# TestReviewEngine — take_snapshot
# =========================================================================

class TestTakeSnapshot:
    def test_score_changes(self, engine):
        entry = _make_decision(
            price=50.0, profitability=4, health=4, cashflow=4,
            valuation=3, growth=3, ownership=4, strategy=4,
        )  # total=26
        engine.record_decision(entry)

        # Scores drop in some dimensions
        new_scores = _scores(
            profitability=4, health=3, cashflow=2,
            valuation=3, growth=3, ownership=4, strategy=4,
        )  # total=23
        snap = engine.take_snapshot("TEST", 45.0, new_scores, entry)

        assert snap.total_score == 23
        assert snap.score_delta == -3
        assert snap.price_change_pct == pytest.approx(-10.0)
        assert "现金流↓" in snap.dimension_changes
        assert "健康↓" in snap.dimension_changes

    def test_alerts_for_deterioration(self, engine):
        entry = _make_decision(
            price=100.0, profitability=5, health=5, cashflow=5,
            valuation=4, growth=4, ownership=4, strategy=4,
        )  # total=31, grade A, signal BUY
        engine.record_decision(entry)

        # Health drops by 3
        new_scores = _scores(
            profitability=5, health=2, cashflow=5,
            valuation=4, growth=4, ownership=4, strategy=4,
        )  # total=28, grade B
        snap = engine.take_snapshot("TEST", 90.0, new_scores, entry)

        assert snap.alerts != ""
        assert "健康大幅下降" in snap.alerts
        assert "评级从A降至B" in snap.alerts

    def test_alerts_for_signal_change(self, engine):
        entry = _make_decision(
            price=100.0, profitability=5, health=5, cashflow=5,
            valuation=5, growth=5, ownership=4, strategy=4,
        )  # total=33, grade A, signal BUY (total>=29 and val>=4)
        engine.record_decision(entry)

        # Valuation drops enough to change signal
        new_scores = _scores(
            profitability=5, health=5, cashflow=5,
            valuation=2, growth=5, ownership=4, strategy=4,
        )  # total=30, still A, but val=2 → HOLD (total>=15 but not BUY)
        snap = engine.take_snapshot("TEST", 110.0, new_scores, entry)

        assert snap.alerts != ""
        assert "信号" in snap.alerts

    def test_no_alerts_when_stable(self, engine):
        entry = _make_decision(
            price=100.0, profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
            signal="HOLD",
        )  # total=28, grade B, signal HOLD
        engine.record_decision(entry)

        # Same scores
        new_scores = _scores(
            profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        snap = engine.take_snapshot("TEST", 105.0, new_scores, entry)

        assert snap.score_delta == 0
        assert snap.dimension_changes == "无变化"
        assert snap.alerts == ""

    def test_snapshot_saved_to_db(self, engine):
        entry = _make_decision(price=50.0)
        engine.record_decision(entry)

        new_scores = _scores(profitability=5, health=3, cashflow=4,
                             valuation=4, growth=4, ownership=4, strategy=4)
        engine.take_snapshot("TEST", 55.0, new_scores, entry)

        snapshots = engine.get_holding_snapshots("TEST")
        assert len(snapshots) == 1
        assert snapshots[0]["current_price"] == 55.0
        assert snapshots[0]["profitability_score"] == 5


# =========================================================================
# TestReviewEngine — generate_review
# =========================================================================

class TestGenerateReview:
    def test_auto_generated_text(self, engine):
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=500,
            profitability=4, health=4, cashflow=4,
            valuation=3, growth=3, ownership=4, strategy=4,
        )  # total=26
        engine.record_decision(entry)

        # Exit with deteriorated cashflow and growth
        exit_scores = _scores(
            profitability=4, health=4, cashflow=2,
            valuation=3, growth=1, ownership=4, strategy=4,
        )  # total=22

        review = engine.generate_review("TEST", "2024-07-01", 90.0, exit_scores)

        assert review.ticker == "TEST"
        assert review.return_pct == pytest.approx(-10.0)
        assert review.pnl == pytest.approx(-5000.0)
        assert review.holding_days == 182
        assert review.entry_total == 26
        assert review.exit_total == 22
        assert review.score_trajectory == "deteriorating"
        assert "现金流" in review.what_was_wrong
        assert "成长" in review.what_was_wrong
        assert "现金流" in review.lessons or "成长" in review.lessons

    def test_score_trajectory_improving(self, engine):
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=3, health=3, cashflow=3,
            valuation=3, growth=3, ownership=3, strategy=3,
        )  # total=21
        engine.record_decision(entry)

        exit_scores = _scores(
            profitability=5, health=5, cashflow=5,
            valuation=5, growth=5, ownership=5, strategy=5,
        )  # total=35
        review = engine.generate_review("TEST", "2024-12-31", 150.0, exit_scores)

        assert review.score_trajectory == "improving"
        assert review.return_pct == pytest.approx(50.0)
        assert review.pnl == pytest.approx(5000.0)
        # what_was_right should mention improvements
        assert "改善" in review.what_was_right or "强势" in review.what_was_right

    def test_review_saved_to_db(self, engine):
        entry = _make_decision(date="2024-01-01", price=100.0, shares=100)
        engine.record_decision(entry)

        exit_scores = _scores()
        engine.generate_review("TEST", "2024-06-01", 110.0, exit_scores)

        reviews = engine.get_reviews("TEST")
        assert len(reviews) == 1
        assert reviews[0]["ticker"] == "TEST"
        assert reviews[0]["return_pct"] == pytest.approx(10.0)

    def test_no_buy_raises(self, engine):
        with pytest.raises(ValueError, match="No BUY decision"):
            engine.generate_review("NOSUCH", "2024-06-01", 100.0, _scores())

    def test_missed_signals_from_snapshots(self, engine):
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=5, health=5, cashflow=5,
            valuation=4, growth=4, ownership=4, strategy=4,
        )  # total=31
        engine.record_decision(entry)

        # Take a snapshot with deteriorating scores (generates alerts)
        bad_scores = _scores(
            profitability=5, health=2, cashflow=5,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        engine.take_snapshot("TEST", 90.0, bad_scores, entry)

        # Now close the position
        exit_scores = _scores(
            profitability=4, health=1, cashflow=4,
            valuation=3, growth=3, ownership=4, strategy=4,
        )
        review = engine.generate_review("TEST", "2024-06-01", 80.0, exit_scores)

        assert review.missed_signals != "无警告信号"
        assert "健康" in review.missed_signals

    def test_what_was_right_strong_dimensions(self, engine):
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        engine.record_decision(entry)

        # Exit with some dimensions at 5
        exit_scores = _scores(
            profitability=5, health=5, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        review = engine.generate_review("TEST", "2024-12-31", 120.0, exit_scores)

        assert "盈利" in review.what_was_right
        assert "健康" in review.what_was_right


# =========================================================================
# TestReviewEngine — generate_weekly_check
# =========================================================================

class TestWeeklyCheck:
    def test_markdown_output(self, engine):
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=4, health=4, cashflow=3,
            valuation=3, growth=4, ownership=4, strategy=4,
        )  # total=26
        engine.record_decision(entry)

        current = _scores(
            profitability=4, health=3, cashflow=3,
            valuation=3, growth=4, ownership=4, strategy=4,
        )
        report = engine.generate_weekly_check("TEST", 110.0, current)

        assert "TEST" in report
        assert "周度持仓检查" in report
        assert "100.00" in report  # entry price
        assert "110.00" in report  # current price
        assert "+10.0%" in report  # price change
        assert "| 盈利 |" in report
        assert "| 健康 |" in report
        assert "评级" in report
        assert "信号" in report

    def test_no_entry_record(self, engine):
        report = engine.generate_weekly_check("NOSUCH", 100.0, _scores())
        assert "未找到买入记录" in report

    def test_alerts_in_weekly(self, engine):
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=5, health=5, cashflow=5,
            valuation=4, growth=4, ownership=4, strategy=4,
        )  # total=31
        engine.record_decision(entry)

        # Big drop in health
        current = _scores(
            profitability=5, health=2, cashflow=5,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        report = engine.generate_weekly_check("TEST", 95.0, current)

        assert "警告信号" in report
        assert "健康" in report

    def test_strong_dimensions_in_weekly(self, engine):
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        engine.record_decision(entry)

        current = _scores(
            profitability=5, health=5, cashflow=5,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        report = engine.generate_weekly_check("TEST", 120.0, current)

        assert "强势维度" in report
        assert "盈利" in report
        assert "健康" in report
        assert "现金流" in report


# =========================================================================
# TestReviewEngine — Full lifecycle
# =========================================================================

class TestFullLifecycle:
    def test_buy_snapshots_sell_review(self, engine):
        """Full lifecycle: buy → snapshots → sell → review."""
        # 1. BUY
        entry = _make_decision(
            ticker="LIFE", date="2024-01-01", price=50.0, shares=200,
            profitability=4, health=4, cashflow=4,
            valuation=3, growth=3, ownership=4, strategy=4,
        )  # total=26, grade B, signal HOLD
        engine.record_decision(entry)

        # 2. Snapshot 1 — slight improvement
        snap1_scores = _scores(
            profitability=4, health=4, cashflow=5,
            valuation=3, growth=3, ownership=4, strategy=4,
        )
        snap1 = engine.take_snapshot("LIFE", 55.0, snap1_scores, entry)
        assert snap1.score_delta == 1
        assert snap1.price_change_pct == pytest.approx(10.0)

        # 3. Snapshot 2 — deterioration
        snap2_scores = _scores(
            profitability=4, health=2, cashflow=3,
            valuation=3, growth=2, ownership=4, strategy=4,
        )
        snap2 = engine.take_snapshot("LIFE", 45.0, snap2_scores, entry)
        assert snap2.score_delta == -4
        assert snap2.price_change_pct == pytest.approx(-10.0)
        assert snap2.alerts != ""  # alerts triggered

        # 4. SELL — generate review
        exit_scores = _scores(
            profitability=4, health=2, cashflow=3,
            valuation=3, growth=2, ownership=4, strategy=4,
        )
        review = engine.generate_review("LIFE", "2024-06-30", 45.0, exit_scores)

        assert review.ticker == "LIFE"
        assert review.entry_price == 50.0
        assert review.exit_price == 45.0
        assert review.return_pct == pytest.approx(-10.0)
        assert review.pnl == pytest.approx(-1000.0)  # (45-50)*200
        assert review.shares == 200
        assert review.holding_days == 181
        assert review.entry_total == 26
        assert review.exit_total == 22
        assert review.score_trajectory == "deteriorating"

        # missed_signals should reference the snapshots
        assert "LIFE" not in review.missed_signals  # ticker not in alerts text
        assert "健康" in review.missed_signals  # health deterioration alert

        # 5. Verify DB state
        assert len(engine.get_decision_history("LIFE")) == 1
        assert len(engine.get_holding_snapshots("LIFE")) == 2
        assert len(engine.get_reviews("LIFE")) == 1


# =========================================================================
# TestReviewEngine — Multiple tickers isolation
# =========================================================================

class TestMultipleTickers:
    def test_ticker_isolation(self, engine):
        """Decisions/snapshots/reviews for different tickers don't mix."""
        # AAPL
        aapl_buy = _make_decision(
            ticker="AAPL", date="2024-01-01", price=150.0, shares=100,
        )
        engine.record_decision(aapl_buy)

        # MSFT
        msft_buy = _make_decision(
            ticker="MSFT", date="2024-02-01", price=300.0, shares=50,
        )
        engine.record_decision(msft_buy)

        # Snapshots
        engine.take_snapshot("AAPL", 160.0, _scores(), aapl_buy)
        engine.take_snapshot("MSFT", 310.0, _scores(), msft_buy)
        engine.take_snapshot("MSFT", 320.0, _scores(), msft_buy)

        # Verify isolation
        assert len(engine.get_decision_history("AAPL")) == 1
        assert len(engine.get_decision_history("MSFT")) == 1
        assert len(engine.get_holding_snapshots("AAPL")) == 1
        assert len(engine.get_holding_snapshots("MSFT")) == 2

        # Reviews
        engine.generate_review("AAPL", "2024-06-01", 170.0, _scores())
        engine.generate_review("MSFT", "2024-07-01", 350.0, _scores())

        assert len(engine.get_reviews("AAPL")) == 1
        assert len(engine.get_reviews("MSFT")) == 1
        assert len(engine.get_reviews()) == 2  # all

        aapl_review = engine.get_reviews("AAPL")[0]
        msft_review = engine.get_reviews("MSFT")[0]
        assert aapl_review["entry_price"] == 150.0
        assert msft_review["entry_price"] == 300.0


# =========================================================================
# TestReviewEngine — Edge cases
# =========================================================================

class TestEdgeCases:
    def test_immediate_sell_no_snapshots(self, engine):
        """Edge case: sell immediately after buying (no snapshots)."""
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        engine.record_decision(entry)

        # Sell same day
        exit_scores = _scores(
            profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        review = engine.generate_review("TEST", "2024-01-01", 100.0, exit_scores)

        assert review.holding_days == 0
        assert review.return_pct == pytest.approx(0.0)
        assert review.pnl == pytest.approx(0.0)
        assert review.score_trajectory == "stable"
        assert review.missed_signals == "无警告信号"

    def test_profitable_exit_improved_scores(self, engine):
        """Edge case: review with improved scores (profitable exit)."""
        entry = _make_decision(
            date="2024-01-01", price=80.0, shares=200,
            profitability=3, health=3, cashflow=3,
            valuation=3, growth=3, ownership=3, strategy=3,
        )  # total=21, grade C
        engine.record_decision(entry)

        # All dimensions improve
        exit_scores = _scores(
            profitability=5, health=5, cashflow=5,
            valuation=5, growth=5, ownership=5, strategy=5,
        )  # total=35, grade A
        review = engine.generate_review("TEST", "2024-12-31", 120.0, exit_scores)

        assert review.return_pct == pytest.approx(50.0)
        assert review.pnl == pytest.approx(8000.0)  # (120-80)*200
        assert review.score_trajectory == "improving"
        assert review.entry_total == 21
        assert review.exit_total == 35
        # what_was_right should have multiple improvement mentions
        assert "改善" in review.what_was_right or "强势" in review.what_was_right
        # what_was_wrong should be "no deterioration"
        assert "无明显恶化" in review.what_was_wrong
        # Lessons should mention thesis validation
        assert "坚持" in review.lessons or "验证" in review.lessons

    def test_get_reviews_all_tickers(self, engine):
        """get_reviews() without ticker returns all."""
        for ticker in ["A", "B", "C"]:
            entry = _make_decision(ticker=ticker, date="2024-01-01", price=100.0)
            engine.record_decision(entry)
            engine.generate_review(ticker, "2024-06-01", 110.0, _scores())

        reviews = engine.get_reviews()
        assert len(reviews) == 3

    def test_get_decision_history_no_filter(self, engine):
        """get_decision_history() without ticker returns all."""
        for ticker in ["X", "Y"]:
            engine.record_decision(
                _make_decision(ticker=ticker, date="2024-01-01")
            )

        all_dec = engine.get_decision_history()
        assert len(all_dec) == 2
        tickers = {d["ticker"] for d in all_dec}
        assert tickers == {"X", "Y"}

    def test_high_valuation_loss_lesson(self, engine):
        """Buying with low valuation score + loss → specific lesson."""
        entry = _make_decision(
            date="2024-01-01", price=200.0, shares=100,
            profitability=4, health=4, cashflow=4,
            valuation=1, growth=4, ownership=4, strategy=4,
        )  # total=25, valuation=1 (overvalued)
        engine.record_decision(entry)

        exit_scores = _scores(
            profitability=3, health=3, cashflow=3,
            valuation=2, growth=3, ownership=4, strategy=4,
        )
        review = engine.generate_review("TEST", "2024-06-01", 150.0, exit_scores)

        assert review.return_pct < 0
        assert "估值" in review.lessons

    def test_weekly_check_with_price_decline(self, engine):
        """Weekly check shows negative price change."""
        entry = _make_decision(
            date="2024-01-01", price=100.0, shares=100,
            profitability=4, health=4, cashflow=4,
            valuation=4, growth=4, ownership=4, strategy=4,
        )
        engine.record_decision(entry)

        report = engine.generate_weekly_check("TEST", 85.0, _scores())
        assert "-15.0%" in report
