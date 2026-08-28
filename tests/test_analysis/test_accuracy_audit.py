"""Tests for the signal accuracy audit module."""

import sys
import os
import json
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.accuracy_audit import AccuracyAuditor


class TestCalculateReturnPct:
    """_calculate_return_pct: (current - signal) / signal."""

    def test_positive_return(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=100.0, current_price=110.0)
        assert result == 0.10

    def test_negative_return(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=100.0, current_price=80.0)
        assert result == -0.20

    def test_zero_return(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=50.0, current_price=50.0)
        assert result == 0.0

    def test_zero_signal_price_returns_none(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=0.0, current_price=50.0)
        assert result is None


class TestIsDirectionCorrect:
    """_is_direction_correct: signal type determines what 'correct' means."""

    def test_buy_price_up_is_correct(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="BUY", signal_price=100.0, current_price=110.0
        )
        assert result is True

    def test_buy_price_down_is_incorrect(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="BUY", signal_price=100.0, current_price=90.0
        )
        assert result is False

    def test_reduce_price_down_is_correct(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="REDUCE", signal_price=100.0, current_price=90.0
        )
        assert result is True

    def test_reduce_price_up_is_incorrect(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="REDUCE", signal_price=100.0, current_price=110.0
        )
        assert result is False

    def test_hold_small_change_is_correct(self):
        """HOLD is correct when |return| < 10%."""
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="HOLD", signal_price=100.0, current_price=105.0
        )
        assert result is True

    def test_hold_large_change_is_incorrect(self):
        """HOLD is incorrect when |return| >= 10%."""
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="HOLD", signal_price=100.0, current_price=115.0
        )
        assert result is False

    def test_watch_always_false(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="WATCH", signal_price=100.0, current_price=110.0
        )
        assert result is False

    def test_signal_price_zero_returns_false(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="BUY", signal_price=0.0, current_price=110.0
        )
        assert result is False


# ---------------------------------------------------------------------------
# Helper: build a fake DuckDB row tuple matching the signal_records columns
# ---------------------------------------------------------------------------
_SIGNAL_COLS = [
    "signal_id", "ticker", "company_name", "signal_date", "signal_type",
    "signal_source", "company_state", "dimension_scores", "total_score", "grade",
    "analysis_details", "user_action", "user_shares", "user_price", "user_date",
    "user_reason", "prediction_6m", "prediction_12m", "actual_6m", "actual_12m",
    "prediction_accuracy", "lessons_learned", "system_improvement", "status",
    "created_at", "updated_at",
]


def _make_row(**overrides):
    """Return a tuple of defaults, overridden by kwargs."""
    defaults = {
        "signal_id": "test-001",
        "ticker": "0700.HK",
        "company_name": "腾讯",
        "signal_date": date.today() - timedelta(days=200),
        "signal_type": "BUY",
        "signal_source": "七维评分",
        "company_state": json.dumps({"price": 350.0, "pe": 15.0, "pb": 3.0}),
        "dimension_scores": json.dumps({"盈利": 4, "健康": 4, "现金流": 3, "估值": 4, "成长": 3, "股东": 3, "战略": 3}),
        "total_score": 24,
        "grade": "C",
        "analysis_details": None,
        "user_action": None,
        "user_shares": 0,
        "user_price": 0.0,
        "user_date": None,
        "user_reason": None,
        "prediction_6m": json.dumps({"expected_price": 400.0, "confidence": 3}),
        "prediction_12m": None,
        "actual_6m": json.dumps({"current_price": 380.0, "date": "2026-02-01"}),
        "actual_12m": None,
        "prediction_accuracy": None,
        "lessons_learned": None,
        "system_improvement": None,
        "status": "active_6m",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    defaults.update(overrides)
    return tuple(defaults[c] for c in _SIGNAL_COLS)


class TestLoadPendingSignals:
    """load_pending_signals: read from DuckDB and parse JSON fields."""

    def test_returns_parsed_records(self):
        """Basic: returns list of dicts with expected keys."""
        row = _make_row()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [row]
        mock_conn.execute.return_value.description = [(c,) for c in _SIGNAL_COLS]

        auditor = AccuracyAuditor(db_path="/tmp/fake.duckdb")
        with patch("analysis.accuracy_audit.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn
            records = auditor.load_pending_signals()

        assert len(records) == 1
        rec = records[0]
        assert rec["signal_id"] == "test-001"
        assert rec["ticker"] == "0700.HK"
        assert rec["company_name"] == "腾讯"
        assert rec["signal_type"] == "BUY"
        assert rec["signal_price"] == 350.0
        assert rec["expected_price_6m"] == 400.0
        assert rec["total_score"] == 24
        assert rec["grade"] == "C"
        assert isinstance(rec["dimension_scores"], dict)
        assert rec["dimension_scores"]["盈利"] == 4
        assert rec["actual_6m"] == {"current_price": 380.0, "date": "2026-02-01"}

    def test_json_none_fields_handled(self):
        """When JSON columns are NULL, result should be None not crash."""
        row = _make_row(
            company_state=None,
            dimension_scores=None,
            prediction_6m=None,
            actual_6m=None,
        )
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [row]
        mock_conn.execute.return_value.description = [(c,) for c in _SIGNAL_COLS]

        auditor = AccuracyAuditor(db_path="/tmp/fake.duckdb")
        with patch("analysis.accuracy_audit.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn
            records = auditor.load_pending_signals()

        rec = records[0]
        assert rec["signal_price"] is None
        assert rec["expected_price_6m"] is None
        assert rec["dimension_scores"] is None
        assert rec["actual_6m"] is None

    def test_min_days_old_filter(self):
        """min_days_old is passed to the SQL WHERE clause."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.description = [(c,) for c in _SIGNAL_COLS]

        auditor = AccuracyAuditor(db_path="/tmp/fake.duckdb")
        with patch("analysis.accuracy_audit.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn
            auditor.load_pending_signals(min_days_old=180)

        # Verify the SQL was called with min_days_old parameter
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        assert "180" in sql or "signal_date" in sql

    def test_empty_result(self):
        """Returns empty list when no records found."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.description = [(c,) for c in _SIGNAL_COLS]

        auditor = AccuracyAuditor(db_path="/tmp/fake.duckdb")
        with patch("analysis.accuracy_audit.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn
            records = auditor.load_pending_signals()

        assert records == []

    def test_read_only_connection(self):
        """Opens DuckDB in read_only mode."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.description = [(c,) for c in _SIGNAL_COLS]

        auditor = AccuracyAuditor(db_path="/tmp/fake.duckdb")
        with patch("analysis.accuracy_audit.duckdb") as mock_duckdb:
            mock_duckdb.connect.return_value = mock_conn
            auditor.load_pending_signals()

        mock_duckdb.connect.assert_called_once_with(
            auditor.db_path, read_only=True
        )


class TestComputeAccuracyStats:
    """compute_accuracy_stats: aggregate accuracy from records."""

    def _make_record(self, signal_type, signal_price, current_price, grade="B", dimension_scores=None):
        """Helper to make a minimal record dict for compute_accuracy_stats."""
        rec = {
            "signal_type": signal_type,
            "signal_price": signal_price,
            "current_price": current_price,
            "grade": grade,
        }
        if dimension_scores is not None:
            rec["dimension_scores"] = dimension_scores
        return rec

    def test_overall_accuracy(self):
        """Correct BUY signals counted accurately."""
        auditor = AccuracyAuditor()
        records = [
            self._make_record("BUY", 100, 110),     # correct
            self._make_record("BUY", 100, 90),       # incorrect
            self._make_record("REDUCE", 100, 90),    # correct
            self._make_record("BUY", 100, 120),      # correct
        ]
        stats = auditor.compute_accuracy_stats(records)
        assert stats["total"] == 4
        assert stats["correct"] == 3
        assert stats["direction_accuracy"] == 0.75

    def test_avg_return_pct(self):
        """Average return calculated correctly."""
        auditor = AccuracyAuditor()
        records = [
            self._make_record("BUY", 100, 110),   # +10%
            self._make_record("BUY", 100, 90),     # -10%
        ]
        stats = auditor.compute_accuracy_stats(records)
        assert abs(stats["avg_return_pct"] - 0.0) < 1e-9

    def test_by_type_breakdown(self):
        """Stats grouped by signal type."""
        auditor = AccuracyAuditor()
        records = [
            self._make_record("BUY", 100, 110),
            self._make_record("BUY", 100, 120),
            self._make_record("REDUCE", 100, 90),
            self._make_record("HOLD", 100, 105),
        ]
        stats = auditor.compute_accuracy_stats(records)
        assert stats["by_type"]["BUY"]["total"] == 2
        assert stats["by_type"]["BUY"]["correct"] == 2
        assert stats["by_type"]["REDUCE"]["total"] == 1
        assert stats["by_type"]["REDUCE"]["correct"] == 1
        assert stats["by_type"]["HOLD"]["total"] == 1

    def test_by_grade_breakdown(self):
        """Stats grouped by grade."""
        auditor = AccuracyAuditor()
        records = [
            self._make_record("BUY", 100, 110, grade="A"),
            self._make_record("BUY", 100, 90, grade="A"),
            self._make_record("REDUCE", 100, 90, grade="B"),
        ]
        stats = auditor.compute_accuracy_stats(records)
        assert stats["by_grade"]["A"]["total"] == 2
        assert stats["by_grade"]["A"]["correct"] == 1
        assert stats["by_grade"]["B"]["total"] == 1
        assert stats["by_grade"]["B"]["correct"] == 1

    def test_by_dimension_predictive_power(self):
        """Dimension analysis: high score accuracy vs low score accuracy."""
        auditor = AccuracyAuditor()
        ds_high = {"盈利": 5, "健康": 4, "现金流": 4, "估值": 4, "成长": 3, "股东": 3, "战略": 3}
        ds_low = {"盈利": 1, "健康": 2, "现金流": 2, "估值": 1, "成长": 2, "股东": 3, "战略": 3}
        records = [
            # High profitability (5) -> price up -> correct BUY
            self._make_record("BUY", 100, 110, dimension_scores=ds_high),
            # High profitability (5) -> price down -> incorrect BUY
            self._make_record("BUY", 100, 90, dimension_scores=ds_high),
            # Low profitability (1) -> price down -> correct REDUCE
            self._make_record("REDUCE", 100, 90, dimension_scores=ds_low),
            # Low profitability (1) -> price up -> incorrect REDUCE
            self._make_record("REDUCE", 100, 120, dimension_scores=ds_low),
        ]
        stats = auditor.compute_accuracy_stats(records)
        prof = stats["by_dimension"]["盈利"]
        # High score (>=3): 2 records, 1 correct -> 0.5
        assert prof["high_count"] == 2
        assert prof["high_score_accuracy"] == 0.5
        # Low score (<3): 2 records, 1 correct -> 0.5
        assert prof["low_count"] == 2
        assert prof["low_score_accuracy"] == 0.5
        # predictive_power = 0.5 - 0.5 = 0.0
        assert prof["predictive_power"] == 0.0

    def test_empty_records(self):
        """Empty input returns sensible defaults."""
        auditor = AccuracyAuditor()
        stats = auditor.compute_accuracy_stats([])
        assert stats["total"] == 0
        assert stats["correct"] == 0
        assert stats["direction_accuracy"] == 0.0
        assert stats["avg_return_pct"] == 0.0

    def test_zero_signal_price_skipped(self):
        """Records with signal_price=0 are excluded from return/accuracy."""
        auditor = AccuracyAuditor()
        records = [
            self._make_record("BUY", 0, 110),      # zero price -> skip
            self._make_record("BUY", 100, 110),     # valid
        ]
        stats = auditor.compute_accuracy_stats(records)
        assert stats["total"] == 2
        # The zero-price record direction is False, so only 1 correct
        assert stats["correct"] == 1

    def test_by_type_has_accuracy_and_avg_return(self):
        """Each type bucket has total, correct, accuracy, avg_return."""
        auditor = AccuracyAuditor()
        records = [
            self._make_record("BUY", 100, 110),
            self._make_record("BUY", 100, 120),
        ]
        stats = auditor.compute_accuracy_stats(records)
        buy = stats["by_type"]["BUY"]
        assert "total" in buy
        assert "correct" in buy
        assert "accuracy" in buy
        assert "avg_return" in buy
        assert buy["accuracy"] == 1.0
        assert abs(buy["avg_return"] - 0.15) < 1e-9  # avg of 0.10 and 0.20


class TestBackfillPrices:
    """backfill_prices method tests."""

    def test_backfill_updates_actual_6m(self, tmp_path):
        """回填后actual_6m字段应包含当前价格"""
        import duckdb as ddb
        db_path = str(tmp_path / "test.duckdb")
        conn = ddb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state JSON, dimension_scores JSON,
                total_score INTEGER, grade VARCHAR, analysis_details JSON,
                user_action VARCHAR, user_shares INTEGER, user_price DOUBLE,
                user_date DATE, user_reason VARCHAR,
                prediction_6m JSON, prediction_12m JSON,
                actual_6m JSON, actual_12m JSON,
                prediction_accuracy JSON, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                't1', '01810.HK', '小米', '2026-05-28', 'BUY', '七维评分',
                '{"price": 20.0}', '{}', 32, 'A', '{}',
                '', 0, 0, NULL, NULL,
                '{"expected_price": 22.0}', NULL, NULL, NULL,
                NULL, '', '', 'active_6m', '2026-05-28', '2026-05-28'
            )
        """)
        conn.close()

        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor(db_path=db_path)

        class MockFetcher:
            def _detect_market(self, ticker):
                return "hk", "01810"
            def fetch_price_hk(self, code):
                return {"close_price": 25.0}

        updated = auditor.backfill_prices(fetcher=MockFetcher())
        assert updated == 1

        conn = ddb.connect(db_path, read_only=True)
        row = conn.execute("SELECT actual_6m FROM signal_records WHERE signal_id='t1'").fetchone()
        conn.close()
        actual = json.loads(row[0])
        assert actual["actual_price"] == 25.0
        assert "backfill_date" in actual

    def test_backfill_skips_existing(self, tmp_path):
        """已有actual_6m的记录不重复回填"""
        import duckdb as ddb
        db_path = str(tmp_path / "test.duckdb")
        conn = ddb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state JSON, dimension_scores JSON,
                total_score INTEGER, grade VARCHAR, analysis_details JSON,
                user_action VARCHAR, user_shares INTEGER, user_price DOUBLE,
                user_date DATE, user_reason VARCHAR,
                prediction_6m JSON, prediction_12m JSON,
                actual_6m JSON, actual_12m JSON,
                prediction_accuracy JSON, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                't1', '01810.HK', '小米', '2026-05-28', 'BUY', '七维评分',
                '{"price": 20.0}', '{}', 32, 'A', '{}',
                '', 0, 0, NULL, NULL,
                '{"expected_price": 22.0}', NULL,
                '{"actual_price": 25.0}', NULL,
                NULL, '', '', 'active_6m', '2026-05-28', '2026-05-28'
            )
        """)
        conn.close()

        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor(db_path=db_path)

        class MockFetcher:
            def _detect_market(self, ticker):
                return "hk", "01810"
            def fetch_price_hk(self, code):
                return {"close_price": 30.0}

        updated = auditor.backfill_prices(fetcher=MockFetcher())
        assert updated == 0  # already has actual_6m


class TestFormatReport:
    """format_report method tests."""

    def test_contains_key_sections(self):
        """报告应包含关键区块"""
        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)

        stats = {
            "total": 100, "correct": 65,
            "direction_accuracy": 0.65,
            "avg_return_pct": 0.03,
            "by_type": {
                "BUY": {"total": 30, "correct": 22, "accuracy": 0.73, "avg_return": 0.08},
                "HOLD": {"total": 50, "correct": 35, "accuracy": 0.70, "avg_return": 0.01},
                "REDUCE": {"total": 20, "correct": 8, "accuracy": 0.40, "avg_return": -0.02},
            },
            "by_grade": {
                "A": {"total": 20, "correct": 17, "accuracy": 0.85, "avg_return": 0.12},
                "B": {"total": 50, "correct": 33, "accuracy": 0.66, "avg_return": 0.03},
                "C": {"total": 30, "correct": 15, "accuracy": 0.50, "avg_return": -0.01},
            },
            "by_dimension": {
                "盈利": {"high_score_accuracy": 0.72, "low_score_accuracy": 0.55,
                         "predictive_power": 0.17, "high_count": 60, "low_count": 40},
            },
        }
        report = auditor.format_report(stats)
        assert "整体方向准确率" in report
        assert "按信号类型" in report
        assert "按评分等级" in report
        assert "维度预测力" in report
        assert "BUY" in report
        assert "65.0%" in report
