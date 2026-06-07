"""信号追踪系统测试"""

import json
import pytest
from datetime import date, timedelta

from src.strategy.signal_tracker import SignalTracker, SignalRecord


@pytest.fixture
def tracker(tmp_path):
    return SignalTracker(db_path=str(tmp_path / "test.duckdb"))


@pytest.fixture
def sample_company_state():
    return {
        "price": 50.0,
        "pe": 15.0,
        "pb": 2.0,
        "revenue": 100000,
        "net_income": 20000,
        "roe": 0.15,
        "gross_margin": 0.35,
        "debt_ratio": 0.4,
        "ocf": 25000,
        "fcf": 15000,
        "shares_outstanding": 1000000,
        "market_cap": 50000000,
    }


@pytest.fixture
def sample_dimension_scores():
    return {
        "盈利能力": 5,
        "成长能力": 4,
        "财务健康": 4,
        "估值水平": 5,
        "现金流": 3,
        "管理层": 4,
        "行业地位": 5,
    }


@pytest.fixture
def sample_analysis_details():
    return {
        "盈利能力": {"ROE检查": "通过", "毛利率检查": "通过"},
        "成长能力": {"营收增长": "通过", "利润增长": "待观察"},
        "财务健康": {"负债率": "通过"},
        "估值水平": {"PE检查": "通过", "PB检查": "通过"},
        "现金流": {"经营现金流": "通过"},
        "管理层": {"分红记录": "通过"},
        "行业地位": {"市场份额": "通过"},
    }


def _create_signal(tracker, cs, ds, ad):
    return tracker.record_signal(
        ticker="600519",
        company_name="贵州茅台",
        signal_date="2024-01-15",
        signal_type="BUY",
        company_state=cs,
        dimension_scores=ds,
        total_score=30,
        grade="A",
        analysis_details=ad,
    )


class TestRecordSignal:
    def test_creates_signal_and_returns_id(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        assert sid is not None
        assert len(sid) == 8

    def test_stores_basic_fields(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        history = tracker.get_signal_history("600519")
        assert len(history) == 1
        rec = history[0]
        assert rec["ticker"] == "600519"
        assert rec["company_name"] == "贵州茅台"
        assert rec["signal_type"] == "BUY"
        assert rec["total_score"] == 30
        assert rec["grade"] == "A"
        assert rec["status"] == "active_6m"

    def test_auto_generates_predictions(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        history = tracker.get_signal_history("600519")
        rec = history[0]

        pred6 = json.loads(rec["prediction_6m"])
        pred12 = json.loads(rec["prediction_12m"])

        assert "expected_price" in pred6
        assert pred6["confidence"] == 3
        assert pred12["confidence"] == 2
        assert pred6["expected_score"] == 30
        assert pred12["expected_score"] == 30

    def test_stores_company_state_as_json(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        history = tracker.get_signal_history("600519")
        cs = json.loads(history[0]["company_state"])
        assert cs["price"] == 50.0
        assert cs["roe"] == 0.15


class TestRecordAction:
    def test_records_action(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_action(sid, "执行买入", user_shares=100, user_price=50.0, user_date="2024-01-16", user_reason="看好长期")

        history = tracker.get_signal_history("600519")
        rec = history[0]
        assert rec["user_action"] == "执行买入"
        assert rec["user_shares"] == 100
        assert rec["user_price"] == 50.0
        assert rec["user_reason"] == "看好长期"

    def test_ignoring_signal(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_action(sid, "忽略信号", user_reason="仓位已满")

        history = tracker.get_signal_history("600519")
        assert history[0]["user_action"] == "忽略信号"
        assert history[0]["user_shares"] == 0


class TestRecordPrediction:
    def test_overrides_auto_prediction(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_prediction(sid, "6m", 60.0, 32, "A+", "BUY", 4, "看好行业趋势")

        history = tracker.get_signal_history("600519")
        pred6 = json.loads(history[0]["prediction_6m"])
        assert pred6["expected_price"] == 60.0
        assert pred6["confidence"] == 4
        assert pred6["reasoning"] == "看好行业趋势"


class TestRecordOutcome:
    def test_records_6m_outcome_and_updates_status(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_outcome(sid, "6m", actual_price=55.0, actual_score=31, actual_grade="A")

        history = tracker.get_signal_history("600519")
        act6 = json.loads(history[0]["actual_6m"])
        assert act6["actual_price"] == 55.0
        assert act6["actual_score"] == 31
        assert history[0]["status"] == "active_12m"

    def test_records_12m_outcome_and_completes(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_outcome(sid, "6m", actual_price=55.0)
        tracker.record_outcome(sid, "12m", actual_price=60.0)

        history = tracker.get_signal_history("600519")
        assert history[0]["status"] == "completed"


class TestGenerateReview:
    def test_computes_accuracy(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        # 预测价格约为50 + 增长调整
        history = tracker.get_signal_history("600519")
        pred6 = json.loads(history[0]["prediction_6m"])
        expected = pred6["expected_price"]

        tracker.record_outcome(sid, "6m", actual_price=expected, actual_score=30)

        review = tracker.generate_review(sid)
        assert "accuracy" in review
        assert "6m" in review["accuracy"]
        assert review["accuracy"]["6m"]["price_accuracy"] > 0.9

    def test_generates_lessons_high_accuracy(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        history = tracker.get_signal_history("600519")
        pred6 = json.loads(history[0]["prediction_6m"])
        expected = pred6["expected_price"]

        tracker.record_outcome(sid, "6m", actual_price=expected, actual_score=30)
        review = tracker.generate_review(sid)
        assert "有效" in review["lessons_learned"] or "准确" in review["lessons_learned"]

    def test_generates_lessons_low_accuracy(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        # 偏差很大的实际价格
        tracker.record_outcome(sid, "6m", actual_price=10.0, actual_score=10)
        review = tracker.generate_review(sid)
        assert "偏差" in review["lessons_learned"] or "改进" in review["lessons_learned"]

    def test_returns_error_for_missing_signal(self, tracker):
        review = tracker.generate_review("nonexistent")
        assert "error" in review


class TestPendingReviews:
    def test_finds_pending_6m_reviews(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        pending = tracker.get_pending_reviews("6m")
        assert len(pending) == 1
        assert pending[0]["ticker"] == "600519"

    def test_empty_after_outcome_recorded(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_outcome(sid, "6m", actual_price=55.0)
        pending = tracker.get_pending_reviews("6m")
        assert len(pending) == 0

    def test_pending_12m_after_6m_recorded(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_outcome(sid, "6m", actual_price=55.0)
        pending_12 = tracker.get_pending_reviews("12m")
        assert len(pending_12) == 1


class TestAccuracyStats:
    def test_empty_when_no_completed(self, tracker):
        stats = tracker.get_accuracy_stats()
        assert stats["total_signals"] == 0

    def test_aggregates_completed_signals(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        history = tracker.get_signal_history("600519")
        pred6 = json.loads(history[0]["prediction_6m"])
        expected = pred6["expected_price"]

        tracker.record_outcome(sid, "6m", actual_price=expected, actual_score=30)
        tracker.generate_review(sid)

        stats = tracker.get_accuracy_stats()
        assert stats["total_signals"] == 1
        assert stats["price_accuracy"] > 0.9


class TestSignalReport:
    def test_generates_markdown(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_action(sid, "执行买入", user_shares=100, user_price=50.0, user_reason="看好")

        report = tracker.generate_signal_report(sid)
        assert "# 信号报告" in report
        assert "600519" in report
        assert "贵州茅台" in report
        assert "七维评分" in report
        assert "执行买入" in report

    def test_report_includes_outcome(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_outcome(sid, "6m", actual_price=55.0, actual_score=31)
        tracker.generate_review(sid)

        report = tracker.generate_signal_report(sid)
        assert "实际结果" in report
        assert "准确度" in report or "经验教训" in report

    def test_returns_not_found(self, tracker):
        report = tracker.generate_signal_report("nonexistent")
        assert "未找到" in report


class TestFullLifecycle:
    def test_complete_chain(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        """完整生命周期：信号→行动→预测→结果→回顾"""
        # Step 1-3: 记录信号（自动生成预测）
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)

        # Step 4: 记录用户行动
        tracker.record_action(sid, "执行买入", user_shares=200, user_price=50.0, user_date="2024-01-16", user_reason="评分优秀")

        # Step 5: 覆盖预测
        tracker.record_prediction(sid, "6m", 58.0, 31, "A", "BUY", 4, "稳健增长预期")

        # Step 6: 记录结果
        tracker.record_outcome(sid, "6m", actual_price=56.0, actual_score=30, actual_grade="A")

        # Step 7: 生成回顾
        review = tracker.generate_review(sid)
        assert review["avg_accuracy"] > 0
        assert review["lessons_learned"]

        # 验证报告
        report = tracker.generate_signal_report(sid)
        assert len(report) > 100

        # 状态应为 active_12m
        history = tracker.get_signal_history("600519")
        assert history[0]["status"] == "active_12m"


class TestMultipleSignals:
    def test_multiple_signals_different_tickers(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid1 = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)

        cs2 = {**sample_company_state, "price": 30.0}
        sid2 = tracker.record_signal(
            ticker="000858",
            company_name="五粮液",
            signal_date="2024-02-01",
            signal_type="WATCH",
            company_state=cs2,
            dimension_scores=sample_dimension_scores,
            total_score=25,
            grade="B+",
            analysis_details=sample_analysis_details,
        )

        assert sid1 != sid2
        all_signals = tracker.get_signal_history()
        assert len(all_signals) == 2

        tracker_signals = tracker.get_signal_history("600519")
        assert len(tracker_signals) == 1

        summary = tracker.generate_tracker_summary()
        assert "600519" in summary
        assert "000858" in summary

    def test_summary_shows_status_counts(self, tracker, sample_company_state, sample_dimension_scores, sample_analysis_details):
        sid = _create_signal(tracker, sample_company_state, sample_dimension_scores, sample_analysis_details)
        tracker.record_outcome(sid, "6m", actual_price=55.0)
        tracker.record_outcome(sid, "12m", actual_price=60.0)

        summary = tracker.generate_tracker_summary()
        assert "已完成" in summary
