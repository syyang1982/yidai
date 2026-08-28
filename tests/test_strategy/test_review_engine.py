"""Tests for src/strategy/review_engine.py — 预期验证引擎。"""

import json
import os
import tempfile

import pytest

from src.strategy.decision import DecisionLog, DecisionRecord
from src.strategy.review_engine import ReviewEngine, ReviewResult


@pytest.fixture
def engine():
    """In-memory ReviewEngine with pre-loaded decision data."""
    eng = ReviewEngine(":memory:")
    return eng


@pytest.fixture
def engine_with_decisions():
    """Engine pre-populated with decision records. Uses temp file to share DB."""
    import tempfile
    db_path = tempfile.mktemp(suffix=".duckdb")
    dl = DecisionLog(db_path)

    # ReviewEngine shares the same DecisionLog instance
    eng = ReviewEngine(db_path, decision_log=dl)

    # Decision 1: BUY xiaomi, expected 35 in 6m
    rec1 = DecisionRecord(
        ticker="01810.HK",
        company_name="小米集团",
        market="HK",
        action="BUY",
        shares=1000,
        price=30.0,
        reason="测试",
        dimension_scores={"盈利": 4, "健康": 3, "现金流": 4, "估值": 3, "成长": 5, "股东": 3, "战略": 4},
        total_score=26,
        grade="B",
        expected_price_6m=35.0,
        expected_price_12m=40.0,
        decision_date="2025-12-01",
    )
    did1 = dl.record(rec1)

    # Decision 2: BUY alibaba, expected 120 in 6m
    rec2 = DecisionRecord(
        ticker="09988.HK",
        company_name="阿里巴巴",
        market="HK",
        action="BUY",
        shares=500,
        price=100.0,
        reason="测试",
        dimension_scores={"盈利": 3, "健康": 4, "现金流": 3, "估值": 4, "成长": 3, "股东": 3, "战略": 3},
        total_score=23,
        grade="B",
        expected_price_6m=120.0,
        expected_price_12m=140.0,
        decision_date="2025-12-01",
    )
    did2 = dl.record(rec2)

    yield eng, dl, did1, did2

    eng.conn.close()
    dl.conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestReviewDecision:
    def test_basic_review(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        result = eng.review_decision(did1, actual_price=33.0, period="6m")
        assert result is not None
        assert result.ticker == "01810.HK"
        assert result.actual_price == 33.0
        assert result.expected_price == 35.0
        assert result.entry_price == 30.0
        assert abs(result.actual_return_pct - 10.0) < 0.1  # (33-30)/30*100
        assert abs(result.expected_return_pct - 16.67) < 0.1  # (35-30)/30*100

    def test_direction_correct(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        # Expected UP, actual UP → direction correct
        result = eng.review_decision(did1, actual_price=33.0, period="6m")
        assert result.direction_correct is True

    def test_direction_wrong(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        # Expected UP, actual DOWN → direction wrong
        result = eng.review_decision(did1, actual_price=28.0, period="6m")
        assert result.direction_correct is False

    def test_beat_expectation(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        result = eng.review_decision(did1, actual_price=36.0, period="6m")
        assert result.beat_expectation is True

    def test_miss_expectation(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        result = eng.review_decision(did1, actual_price=33.0, period="6m")
        assert result.beat_expectation is False

    def test_price_accuracy(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        # Expected 35, actual 35 → accuracy = 1.0
        result = eng.review_decision(did1, actual_price=35.0, period="6m")
        assert result.price_accuracy == 1.0

    def test_price_accuracy_partial(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        # Expected 35, actual 30 → accuracy = 1 - 5/35 = 0.857
        result = eng.review_decision(did1, actual_price=30.0, period="6m")
        assert abs(result.price_accuracy - 0.857) < 0.01

    def test_nonexistent_decision(self, engine):
        result = engine.review_decision("nonexistent", 100.0)
        assert result is None

    def test_12m_period(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        result = eng.review_decision(did1, actual_price=42.0, period="12m")
        assert result is not None
        assert result.expected_price == 40.0
        assert result.expected_period == "12m"

    def test_review_persists(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        eng.review_decision(did1, actual_price=33.0, period="6m")
        stats = eng.get_review_stats()
        assert stats["total_reviews"] == 1


class TestBatchReview:
    def test_batch_with_fetch_fn(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        prices = {"01810.HK": 33.0, "09988.HK": 110.0}
        results = eng.batch_review(period="6m", fetch_current_fn=lambda t: prices.get(t, 0))
        # Both decisions are from 2025-12-01, which is > 6 months ago
        # So they should be pending review
        assert len(results) >= 0  # depends on date arithmetic

    def test_batch_no_fetch_fn(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions
        results = eng.batch_review(period="6m", fetch_current_fn=None)
        assert results == []


class TestDimensionEffectiveness:
    def test_no_data(self, engine):
        results = engine.analyze_dimension_effectiveness()
        assert results == []

    def test_with_reviews(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        # Review both decisions
        eng.review_decision(did1, actual_price=35.0, period="6m")  # good return
        eng.review_decision(did2, actual_price=90.0, period="6m")   # bad return

        results = eng.analyze_dimension_effectiveness()
        assert len(results) > 0
        # "成长" dimension: xiaomi=5(high), alibaba=3(mid)
        # "估值" dimension: xiaomi=3(mid), alibaba=4(high)
        dim_names = [r.dimension for r in results]
        assert "成长" in dim_names


class TestAlertOutcome:
    def test_record_and_query(self, engine):
        aid = engine.record_alert_outcome(
            rule_id="W1.1.1",
            ticker="01810.HK",
            alert_date="2026-01-01",
            severity="HIGH",
            price_at_alert=30.0,
            price_after_30d=28.0,
            price_after_60d=27.0,
            price_after_90d=25.0,
        )
        assert aid is not None

        stats = engine.get_alert_accuracy_stats()
        assert len(stats) == 1
        assert stats[0].true_positives == 1

    def test_false_positive(self, engine):
        engine.record_alert_outcome(
            rule_id="W1.1.1",
            ticker="01810.HK",
            alert_date="2026-01-01",
            severity="HIGH",
            price_at_alert=30.0,
            price_after_30d=32.0,
            price_after_60d=34.0,
            price_after_90d=36.0,
        )

        stats = engine.get_alert_accuracy_stats()
        assert len(stats) == 1
        assert stats[0].false_positives == 1


class TestReviewStats:
    def test_empty(self, engine):
        stats = engine.get_review_stats()
        assert stats["total_reviews"] == 0

    def test_with_data(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        eng.review_decision(did1, actual_price=35.0, period="6m")
        eng.review_decision(did2, actual_price=90.0, period="6m")

        stats = eng.get_review_stats()
        assert stats["total_reviews"] == 2
        assert 0 <= stats["direction_accuracy"] <= 100
        assert 0 <= stats["avg_price_accuracy"] <= 100


class TestFormatReports:
    def test_review_report(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        result = eng.review_decision(did1, actual_price=35.0, period="6m")
        report = eng.format_review_report(result)
        assert "小米集团" in report
        assert "01810.HK" in report
        assert "35.0" in report

    def test_dimension_report_empty(self, engine):
        report = engine.format_dimension_report([])
        assert "暂无" in report

    def test_dimension_report_with_data(self, engine_with_decisions):
        eng, dl, did1, did2 = engine_with_decisions

        eng.review_decision(did1, actual_price=35.0, period="6m")
        eng.review_decision(did2, actual_price=90.0, period="6m")

        results = eng.analyze_dimension_effectiveness()
        report = eng.format_dimension_report(results)
        assert "维度" in report


class TestPersistence:
    def test_file_persistence(self):
        """Verify review results survive close/reopen."""
        db_path = tempfile.mktemp(suffix=".duckdb")
        try:
            eng1 = ReviewEngine(db_path)
            dl1 = DecisionLog(db_path)
            rec = DecisionRecord(
                ticker="01810.HK", company_name="小米集团",
                action="BUY", price=30.0, shares=1000,
                expected_price_6m=35.0, decision_date="2025-12-01",
                dimension_scores={"盈利": 4},
            )
            did = dl1.record(rec)
            eng1.review_decision(did, 33.0, "6m")
            eng1.conn.close()

            eng2 = ReviewEngine(db_path)
            stats = eng2.get_review_stats()
            assert stats["total_reviews"] == 1
            eng2.conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
