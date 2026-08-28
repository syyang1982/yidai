"""Tests for src/strategy/decision.py — 决策日志系统。"""

import json
import os
import tempfile

import pytest

from src.strategy.decision import DecisionLog, DecisionRecord


@pytest.fixture
def log():
    """In-memory DecisionLog."""
    return DecisionLog(":memory:")


@pytest.fixture
def sample_record():
    """A sample decision record for testing."""
    return DecisionRecord(
        ticker="01810.HK",
        company_name="小米集团",
        market="HK",
        action="BUY",
        shares=1000,
        price=30.5,
        currency="HKD",
        reason="七维评分A级，估值合理",
        thesis="AI+汽车+IoT生态长期看好",
        catalyst="SU7交付超预期",
        risk_note="手机业务利润率承压",
        dimension_scores={"盈利": 4, "健康": 4, "现金流": 4, "估值": 3, "成长": 5, "股东": 3, "战略": 4},
        total_score=27,
        grade="B",
        signal="BUY",
        expected_price_6m=35.0,
        expected_price_12m=40.0,
        expected_reasoning="假设汽车业务2026年贡献10%营收",
        decision_date="2026-06-01",
    )


class TestDecisionRecord:
    def test_defaults(self):
        rec = DecisionRecord()
        assert rec.ticker == ""
        assert rec.action == ""
        assert rec.shares == 0
        assert rec.status == "active"
        assert rec.dimension_scores == {}

    def test_amount_auto_calc(self, log, sample_record):
        """amount should auto-calculate from shares * price."""
        did = log.record(sample_record)
        rec = log.get(did)
        assert rec.amount == 1000 * 30.5

    def test_explicit_amount_preserved(self, log, sample_record):
        """Explicit amount should not be overwritten."""
        sample_record.amount = 99999
        did = log.record(sample_record)
        rec = log.get(did)
        assert rec.amount == 99999


class TestDecisionLog:
    def test_record_and_get(self, log, sample_record):
        did = log.record(sample_record)
        assert did is not None and len(did) == 8

        rec = log.get(did)
        assert rec is not None
        assert rec.ticker == "01810.HK"
        assert rec.company_name == "小米集团"
        assert rec.action == "BUY"
        assert rec.shares == 1000
        assert rec.price == 30.5
        assert rec.total_score == 27
        assert rec.grade == "B"
        assert rec.signal == "BUY"
        assert rec.dimension_scores["盈利"] == 4

    def test_record_generates_id(self, log, sample_record):
        sample_record.decision_id = ""
        did = log.record(sample_record)
        assert len(did) == 8

    def test_record_preserves_id(self, log, sample_record):
        sample_record.decision_id = "custom-id"
        did = log.record(sample_record)
        assert did == "custom-id"

    def test_get_nonexistent(self, log):
        assert log.get("nonexistent") is None

    def test_list_all(self, log, sample_record):
        log.record(sample_record)
        sample_record.decision_id = ""
        sample_record.ticker = "09988.HK"
        sample_record.company_name = "阿里巴巴"
        log.record(sample_record)

        all_recs = log.list_decisions()
        assert len(all_recs) == 2

    def test_list_filter_ticker(self, log, sample_record):
        log.record(sample_record)
        sample_record.decision_id = ""
        sample_record.ticker = "09988.HK"
        log.record(sample_record)

        filtered = log.list_decisions(ticker="01810.HK")
        assert len(filtered) == 1
        assert filtered[0].ticker == "01810.HK"

    def test_list_filter_action(self, log, sample_record):
        log.record(sample_record)
        sample_record.decision_id = ""
        sample_record.action = "SELL"
        log.record(sample_record)

        buys = log.list_decisions(action="BUY")
        assert len(buys) == 1
        sells = log.list_decisions(action="SELL")
        assert len(sells) == 1

    def test_list_limit(self, log, sample_record):
        for i in range(5):
            sample_record.decision_id = ""
            sample_record.decision_date = f"2026-06-{i+1:02d}"
            log.record(sample_record)
        limited = log.list_decisions(limit=3)
        assert len(limited) == 3

    def test_list_ordered_by_date_desc(self, log, sample_record):
        for i in range(3):
            sample_record.decision_id = ""
            sample_record.decision_date = f"2026-06-{i+1:02d}"
            log.record(sample_record)
        recs = log.list_decisions()
        dates = [r.decision_date for r in recs]
        assert dates == sorted(dates, reverse=True)


class TestRecordOutcome:
    def test_record_6m_outcome(self, log, sample_record):
        did = log.record(sample_record)
        log.record_outcome(did, actual_price=35.0, period="6m", review_notes="符合预期")
        rec = log.get(did)
        assert rec.actual_price_6m == 35.0
        assert rec.review_notes == "符合预期"
        assert rec.status == "reviewed_6m"

    def test_record_12m_outcome_with_return(self, log, sample_record):
        did = log.record(sample_record)
        log.record_outcome(
            did, actual_price=40.0, period="12m",
            review_notes="超预期", lessons="估值容忍度可以更高",
        )
        rec = log.get(did)
        assert rec.actual_price_12m == 40.0
        assert abs(rec.actual_return_pct - ((40 - 30.5) / 30.5 * 100)) < 0.1
        assert rec.lessons == "估值容忍度可以更高"
        assert rec.status == "reviewed_12m"

    def test_record_outcome_nonexistent(self, log):
        result = log.record_outcome("nonexistent", 100.0)
        assert result is False


class TestPendingReviews:
    def test_no_pending(self, log, sample_record):
        log.record(sample_record)
        pending = log.get_pending_reviews("6m")
        # Recent decision shouldn't be pending
        assert len(pending) == 0


class TestStats:
    def test_empty_stats(self, log):
        stats = log.get_stats()
        assert stats["total_decisions"] == 0
        assert stats["reviewed"] == 0

    def test_stats_with_data(self, log, sample_record):
        log.record(sample_record)
        sample_record.decision_id = ""
        sample_record.action = "SELL"
        sample_record.ticker = "09988.HK"
        log.record(sample_record)

        stats = log.get_stats()
        assert stats["total_decisions"] == 2
        assert stats["by_action"]["BUY"] == 1
        assert stats["by_action"]["SELL"] == 1


class TestToMarkdown:
    def test_basic_markdown(self, log, sample_record):
        did = log.record(sample_record)
        rec = log.get(did)
        md = log.to_markdown(rec)

        assert "小米集团" in md
        assert "01810.HK" in md
        assert "BUY" in md
        assert "1000" in md
        assert "30.5" in md
        assert "27/35" in md
        assert "B" in md
        assert "SU7" in md

    def test_markdown_with_outcome(self, log, sample_record):
        did = log.record(sample_record)
        log.record_outcome(did, 35.0, "6m", "符合预期")
        rec = log.get(did)
        md = log.to_markdown(rec)
        assert "reviewed_6m" in md
        assert "35.0" in md


class TestPersistence:
    def test_file_persistence(self, sample_record):
        """Verify data survive close/reopen."""
        path = tempfile.mktemp(suffix=".duckdb")
        try:
            log1 = DecisionLog(path)
            did = log1.record(sample_record)
            log1.conn.close()

            log2 = DecisionLog(path)
            rec = log2.get(did)
            assert rec is not None
            assert rec.ticker == "01810.HK"
            assert rec.dimension_scores["盈利"] == 4
            log2.conn.close()
        finally:
            os.unlink(path)


class TestEdgeCases:
    def test_hold_action_zero_shares(self, log):
        rec = DecisionRecord(
            ticker="01810.HK",
            company_name="小米集团",
            action="HOLD",
            shares=0,
            price=32.0,
            reason="维持现有仓位",
            decision_date="2026-06-01",
        )
        did = log.record(rec)
        saved = log.get(did)
        assert saved.action == "HOLD"
        assert saved.shares == 0
        assert saved.amount == 0

    def test_sell_action(self, log):
        rec = DecisionRecord(
            ticker="01810.HK",
            company_name="小米集团",
            action="REDUCE",
            shares=2000,
            price=33.0,
            reason="减仓锁定利润",
            decision_date="2026-06-01",
        )
        did = log.record(rec)
        saved = log.get(did)
        assert saved.action == "REDUCE"
        assert saved.amount == 2000 * 33.0

    def test_empty_dimension_scores(self, log):
        rec = DecisionRecord(
            ticker="01810.HK",
            company_name="小米集团",
            action="HOLD",
            price=32.0,
            reason="观望",
            decision_date="2026-06-01",
        )
        did = log.record(rec)
        saved = log.get(did)
        assert saved.dimension_scores == {}
        assert saved.total_score == 0
