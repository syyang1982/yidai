"""Tests for backfill_prices, format_report, and generate_full_report."""

import sys
import os
import json
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.accuracy_audit import AccuracyAuditor


class TestBackfillPrices:
    """backfill_prices: fetch current prices and update actual_6m in DuckDB."""

    def test_backfill_updates_null_actual_6m(self, tmp_path):
        """Records with NULL actual_6m get updated with fetched price."""

        db_path = tmp_path / "signals.duckdb"

        # Create a real DuckDB with the schema
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state VARCHAR, dimension_scores VARCHAR,
                total_score INTEGER, grade VARCHAR,
                analysis_details VARCHAR, user_action VARCHAR,
                user_shares INTEGER, user_price DOUBLE, user_date DATE,
                user_reason VARCHAR, prediction_6m VARCHAR, prediction_12m VARCHAR,
                actual_6m VARCHAR, actual_12m VARCHAR,
                prediction_accuracy VARCHAR, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                'test-001', '0700.HK', '腾讯', '2026-01-01', 'BUY', '七维评分',
                '{"price": 350.0}', '{"盈利": 4}', 24, 'C',
                NULL, NULL, 0, 0.0, NULL, NULL,
                '{"expected_price": 400.0}', NULL,
                NULL, NULL, NULL, NULL, NULL, 'active_6m',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                'test-002', '600519.SH', '茅台', '2026-01-01', 'BUY', '七维评分',
                '{"price": 1800.0}', '{"盈利": 5}', 28, 'A',
                NULL, NULL, 0, 0.0, NULL, NULL,
                '{"expected_price": 2000.0}', NULL,
                '{"actual_price": 1900.0, "backfill_date": "2026-07-01"}', NULL, NULL, NULL, NULL, 'active_6m',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """)
        conn.close()

        # Mock fetcher
        mock_fetcher = MagicMock()
        mock_fetcher._detect_market.side_effect = lambda t: {
            "0700.HK": ("hk", "0700"),
            "600519.SH": ("a_share", "600519"),
        }[t]
        mock_fetcher.fetch_price_hk.return_value = {"close_price": 380.0}
        mock_fetcher.fetch_price_a_share.return_value = {"close_price": 1900.0}

        auditor = AccuracyAuditor(db_path=db_path)
        updated = auditor.backfill_prices(fetcher=mock_fetcher, max_records=100)

        # Only test-001 should be updated (test-002 already has actual_6m)
        assert updated == 1
        mock_fetcher.fetch_price_hk.assert_called_once_with("0700")

        # Verify the update was written
        conn = duckdb.connect(db_path, read_only=True)
        row = conn.execute(
            "SELECT actual_6m FROM signal_records WHERE signal_id = 'test-001'"
        ).fetchone()
        conn.close()
        actual = json.loads(row[0])
        assert actual["actual_price"] == 380.0
        assert "backfill_date" in actual

    def test_backfill_respects_max_records(self, tmp_path):
        """Only processes up to max_records."""

        db_path = tmp_path / "signals.duckdb"
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state VARCHAR, dimension_scores VARCHAR,
                total_score INTEGER, grade VARCHAR,
                analysis_details VARCHAR, user_action VARCHAR,
                user_shares INTEGER, user_price DOUBLE, user_date DATE,
                user_reason VARCHAR, prediction_6m VARCHAR, prediction_12m VARCHAR,
                actual_6m VARCHAR, actual_12m VARCHAR,
                prediction_accuracy VARCHAR, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        for i in range(5):
            conn.execute(f"""
                INSERT INTO signal_records VALUES (
                    'test-{i:03d}', '0700.HK', '腾讯', '2026-01-01', 'BUY', '七维评分',
                    '{{"price": 350.0}}', '{{"盈利": 4}}', 24, 'C',
                    NULL, NULL, 0, 0.0, NULL, NULL,
                    '{{"expected_price": 400.0}}', NULL,
                    NULL, NULL, NULL, NULL, NULL, 'active_6m',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """)
        conn.close()

        mock_fetcher = MagicMock()
        mock_fetcher._detect_market.return_value = ("hk", "0700")
        mock_fetcher.fetch_price_hk.return_value = {"close_price": 380.0}

        auditor = AccuracyAuditor(db_path=db_path)
        updated = auditor.backfill_prices(fetcher=mock_fetcher, max_records=2)

        assert updated == 2
        assert mock_fetcher.fetch_price_hk.call_count == 2

    def test_backfill_uses_default_fetcher_when_none(self, tmp_path):
        """When fetcher=None, creates EastmoneyFetcher internally."""

        db_path = tmp_path / "signals.duckdb"
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state VARCHAR, dimension_scores VARCHAR,
                total_score INTEGER, grade VARCHAR,
                analysis_details VARCHAR, user_action VARCHAR,
                user_shares INTEGER, user_price DOUBLE, user_date DATE,
                user_reason VARCHAR, prediction_6m VARCHAR, prediction_12m VARCHAR,
                actual_6m VARCHAR, actual_12m VARCHAR,
                prediction_accuracy VARCHAR, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.close()

        auditor = AccuracyAuditor(db_path=db_path)
        with patch("src.data.fetcher.EastmoneyFetcher") as MockFetcher:
            mock_instance = MagicMock()
            MockFetcher.return_value = mock_instance
            # No records to process, just verify the import works
            updated = auditor.backfill_prices()

        assert updated == 0
        MockFetcher.assert_called_once()

    def test_backfill_handles_fetch_error_gracefully(self, tmp_path):
        """When price fetch fails, skips that record and continues."""

        db_path = tmp_path / "signals.duckdb"
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state VARCHAR, dimension_scores VARCHAR,
                total_score INTEGER, grade VARCHAR,
                analysis_details VARCHAR, user_action VARCHAR,
                user_shares INTEGER, user_price DOUBLE, user_date DATE,
                user_reason VARCHAR, prediction_6m VARCHAR, prediction_12m VARCHAR,
                actual_6m VARCHAR, actual_12m VARCHAR,
                prediction_accuracy VARCHAR, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                'test-001', '0700.HK', '腾讯', '2026-01-01', 'BUY', '七维评分',
                '{"price": 350.0}', '{"盈利": 4}', 24, 'C',
                NULL, NULL, 0, 0.0, NULL, NULL,
                '{"expected_price": 400.0}', NULL,
                NULL, NULL, NULL, NULL, NULL, 'active_6m',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """)
        conn.close()

        mock_fetcher = MagicMock()
        mock_fetcher._detect_market.return_value = ("hk", "0700")
        mock_fetcher.fetch_price_hk.return_value = {"close_price": None}  # no price

        auditor = AccuracyAuditor(db_path=db_path)
        updated = auditor.backfill_prices(fetcher=mock_fetcher)

        # close_price is None, so actual_6m should be written with None price
        # but the record should still be counted as updated
        assert updated == 1

    def test_backfill_a_share_market(self, tmp_path):
        """A-share tickers use fetch_price_a_share."""

        db_path = tmp_path / "signals.duckdb"
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state VARCHAR, dimension_scores VARCHAR,
                total_score INTEGER, grade VARCHAR,
                analysis_details VARCHAR, user_action VARCHAR,
                user_shares INTEGER, user_price DOUBLE, user_date DATE,
                user_reason VARCHAR, prediction_6m VARCHAR, prediction_12m VARCHAR,
                actual_6m VARCHAR, actual_12m VARCHAR,
                prediction_accuracy VARCHAR, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                'test-001', '600519.SH', '茅台', '2026-01-01', 'BUY', '七维评分',
                '{"price": 1800.0}', '{"盈利": 5}', 28, 'A',
                NULL, NULL, 0, 0.0, NULL, NULL,
                '{"expected_price": 2000.0}', NULL,
                NULL, NULL, NULL, NULL, NULL, 'active_6m',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """)
        conn.close()

        mock_fetcher = MagicMock()
        mock_fetcher._detect_market.return_value = ("a_share", "600519")
        mock_fetcher.fetch_price_a_share.return_value = {"close_price": 1850.0}

        auditor = AccuracyAuditor(db_path=db_path)
        updated = auditor.backfill_prices(fetcher=mock_fetcher)

        assert updated == 1
        mock_fetcher.fetch_price_a_share.assert_called_once_with("600519")
        mock_fetcher.fetch_price_hk.assert_not_called()


class TestFormatReport:
    """format_report: terminal-formatted accuracy report."""

    def test_contains_header(self):

        auditor = AccuracyAuditor()
        stats = {
            "total": 100, "correct": 65, "direction_accuracy": 0.65,
            "avg_return_pct": 0.03,
            "by_type": {}, "by_grade": {}, "by_dimension": {},
        }
        report = auditor.format_report(stats)
        assert "信号准确率审计报告" in report

    def test_contains_overall_accuracy(self):

        auditor = AccuracyAuditor()
        stats = {
            "total": 100, "correct": 65, "direction_accuracy": 0.65,
            "avg_return_pct": 0.03,
            "by_type": {}, "by_grade": {}, "by_dimension": {},
        }
        report = auditor.format_report(stats)
        assert "65.0%" in report
        assert "100" in report

    def test_contains_by_type_section(self):

        auditor = AccuracyAuditor()
        stats = {
            "total": 4, "correct": 3, "direction_accuracy": 0.75,
            "avg_return_pct": 0.05,
            "by_type": {
                "BUY": {"total": 2, "correct": 2, "accuracy": 1.0, "avg_return": 0.10},
                "REDUCE": {"total": 1, "correct": 1, "accuracy": 1.0, "avg_return": -0.05},
                "HOLD": {"total": 1, "correct": 0, "accuracy": 0.0, "avg_return": 0.03},
            },
            "by_grade": {}, "by_dimension": {},
        }
        report = auditor.format_report(stats)
        assert "按信号类型" in report
        assert "BUY" in report
        assert "REDUCE" in report
        assert "HOLD" in report

    def test_contains_by_grade_section(self):

        auditor = AccuracyAuditor()
        stats = {
            "total": 3, "correct": 2, "direction_accuracy": 0.67,
            "avg_return_pct": 0.05,
            "by_type": {},
            "by_grade": {
                "A": {"total": 1, "correct": 1, "accuracy": 1.0, "avg_return": 0.12},
                "B": {"total": 1, "correct": 1, "accuracy": 1.0, "avg_return": 0.03},
                "C": {"total": 1, "correct": 0, "accuracy": 0.0, "avg_return": -0.01},
            },
            "by_dimension": {},
        }
        report = auditor.format_report(stats)
        assert "按评分等级" in report
        assert "A" in report and "B" in report and "C" in report

    def test_contains_by_dimension_section(self):

        auditor = AccuracyAuditor()
        stats = {
            "total": 4, "correct": 2, "direction_accuracy": 0.5,
            "avg_return_pct": 0.0,
            "by_type": {}, "by_grade": {},
            "by_dimension": {
                "盈利": {
                    "high_score_accuracy": 0.72,
                    "low_score_accuracy": 0.55,
                    "high_count": 50, "low_count": 50,
                    "predictive_power": 0.17,
                },
                "估值": {
                    "high_score_accuracy": 0.60,
                    "low_score_accuracy": 0.55,
                    "high_count": 40, "low_count": 60,
                    "predictive_power": 0.05,
                },
            },
        }
        report = auditor.format_report(stats)
        assert "维度预测力" in report
        assert "盈利" in report
        assert "估值" in report

    def test_empty_stats(self):

        auditor = AccuracyAuditor()
        stats = {
            "total": 0, "correct": 0, "direction_accuracy": 0.0,
            "avg_return_pct": 0.0,
            "by_type": {}, "by_grade": {}, "by_dimension": {},
        }
        report = auditor.format_report(stats)
        assert "0.0%" in report


class TestGenerateFullReport:
    """generate_full_report: load data, compute stats, return full report."""

    def test_returns_stats_dict(self, tmp_path):

        db_path = tmp_path / "signals.duckdb"
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state VARCHAR, dimension_scores VARCHAR,
                total_score INTEGER, grade VARCHAR,
                analysis_details VARCHAR, user_action VARCHAR,
                user_shares INTEGER, user_price DOUBLE, user_date DATE,
                user_reason VARCHAR, prediction_6m VARCHAR, prediction_12m VARCHAR,
                actual_6m VARCHAR, actual_12m VARCHAR,
                prediction_accuracy VARCHAR, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                'test-001', '0700.HK', '腾讯', '2026-01-01', 'BUY', '七维评分',
                '{"price": 350.0}', '{"盈利": 4}', 24, 'C',
                NULL, NULL, 0, 0.0, NULL, NULL,
                '{"expected_price": 400.0}', NULL,
                '{"actual_price": 380.0, "backfill_date": "2026-07-01"}', NULL, NULL, NULL, NULL, 'active_6m',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                'test-002', '0700.HK', '腾讯', '2026-01-01', 'BUY', '七维评分',
                '{"price": 350.0}', '{"盈利": 3}', 20, 'B',
                NULL, NULL, 0, 0.0, NULL, NULL,
                '{"expected_price": 300.0}', NULL,
                NULL, NULL, NULL, NULL, NULL, 'active_6m',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """)
        conn.close()

        auditor = AccuracyAuditor.__new__(AccuracyAuditor)
        auditor.db_path = db_path
        # Skip _ensure_time_window_column since table has no time_window_prices col
        stats = auditor.generate_full_report()

        # generate_full_report now returns {"windows": {...}, "overall": {...}}
        assert "overall" in stats
        assert "windows" in stats
        overall = stats["overall"]
        # test-001 has actual_6m -> current_price=380.0 -> BUY at 350->380 = correct
        assert overall["total"] == 1
        assert overall["correct"] == 1
        assert overall["direction_accuracy"] == 1.0

    def test_empty_db(self, tmp_path):

        db_path = tmp_path / "signals.duckdb"
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state VARCHAR, dimension_scores VARCHAR,
                total_score INTEGER, grade VARCHAR,
                analysis_details VARCHAR, user_action VARCHAR,
                user_shares INTEGER, user_price DOUBLE, user_date DATE,
                user_reason VARCHAR, prediction_6m VARCHAR, prediction_12m VARCHAR,
                actual_6m VARCHAR, actual_12m VARCHAR,
                prediction_accuracy VARCHAR, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.close()

        auditor = AccuracyAuditor.__new__(AccuracyAuditor)
        auditor.db_path = db_path
        stats = auditor.generate_full_report()

        assert "overall" in stats
        assert stats["overall"]["total"] == 0
