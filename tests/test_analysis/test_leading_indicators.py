"""Tests for the leading indicators tracking module."""

import os
import sys
import tempfile

import duckdb
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.leading_indicators import LeadingIndicatorStore


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary DuckDB database path."""
    return str(tmp_path / "test_leading.duckdb")


@pytest.fixture
def store(tmp_db):
    """Provide a fresh LeadingIndicatorStore instance."""
    s = LeadingIndicatorStore(tmp_db)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# test_create_table: table creation
# ---------------------------------------------------------------------------


class TestCreateTable:
    def test_table_exists(self, store):
        """leading_indicators table should be created on init."""
        result = store.conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'leading_indicators'"
        ).fetchone()
        assert result is not None
        assert result[0] == "leading_indicators"

    def test_table_columns(self, store):
        """Table should have all expected columns."""
        cols = store.conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'leading_indicators' ORDER BY column_name"
        ).fetchall()
        col_names = {c[0] for c in cols}
        expected = {
            "ticker", "company_name", "indicator_name", "description", "source",
            "threshold_positive", "threshold_negative", "unit", "category",
            "latest_value", "latest_period", "latest_date", "status",
            "notes", "created_at", "updated_at",
        }
        assert expected.issubset(col_names)

    def test_primary_key(self, store):
        """PRIMARY KEY should be (ticker, indicator_name)."""
        pk = store.conn.execute(
            "SELECT constraint_type FROM information_schema.table_constraints "
            "WHERE table_name = 'leading_indicators' AND constraint_type = 'PRIMARY KEY'"
        ).fetchone()
        assert pk is not None

    def test_idempotent_creation(self, tmp_db):
        """Creating the store twice should not raise."""
        s1 = LeadingIndicatorStore(tmp_db)
        s2 = LeadingIndicatorStore(tmp_db)
        s1.close()
        s2.close()


# ---------------------------------------------------------------------------
# test_add_indicator: adding a leading indicator
# ---------------------------------------------------------------------------


class TestAddIndicator:
    def test_add_single_indicator(self, store):
        """Should insert a new indicator record."""
        store.add_indicator(
            ticker="LX",
            company_name="乐信",
            indicator_name="take_rate",
            description="Take rate (平台服务费率)",
            source="earnings_call",
            threshold_positive=15.0,
            threshold_negative=8.0,
            unit="%",
            category="revenue_quality",
        )
        rows = store.conn.execute("SELECT * FROM leading_indicators WHERE ticker = 'LX'").fetchall()
        assert len(rows) == 1

    def test_add_returns_dict(self, store):
        """add_indicator should return the stored record as dict."""
        result = store.add_indicator(
            ticker="LX",
            company_name="乐信",
            indicator_name="take_rate",
            description="Take rate",
            source="earnings_call",
            threshold_positive=15.0,
            threshold_negative=8.0,
            unit="%",
            category="revenue_quality",
        )
        assert isinstance(result, dict)
        assert result["ticker"] == "LX"
        assert result["indicator_name"] == "take_rate"

    def test_upsert_on_duplicate(self, store):
        """Adding the same (ticker, indicator_name) should update, not duplicate."""
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="v1", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="v2 updated", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        rows = store.conn.execute(
            "SELECT description FROM leading_indicators WHERE ticker = 'LX' AND indicator_name = 'take_rate'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "v2 updated"

    def test_multiple_indicators(self, store):
        """Should support multiple indicators for the same ticker."""
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="active_users",
            description="Active users", source="s", threshold_positive=1000000,
            threshold_negative=500000, unit="users", category="engagement",
        )
        rows = store.conn.execute("SELECT * FROM leading_indicators WHERE ticker = 'LX'").fetchall()
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# test_update_value: updating indicator values
# ---------------------------------------------------------------------------


class TestUpdateValue:
    def _add_default(self, store):
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="earnings", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )

    def test_update_sets_value(self, store):
        """update_value should set latest_value and latest_period."""
        self._add_default(store)
        store.update_value("LX", "take_rate", 12.5, "2026Q2")
        row = store.conn.execute(
            "SELECT latest_value, latest_period FROM leading_indicators WHERE ticker = 'LX' AND indicator_name = 'take_rate'"
        ).fetchone()
        assert row[0] == 12.5
        assert row[1] == "2026Q2"

    def test_update_sets_date(self, store):
        """update_value should set latest_date to current date."""
        self._add_default(store)
        store.update_value("LX", "take_rate", 12.5, "2026Q2")
        row = store.conn.execute(
            "SELECT latest_date FROM leading_indicators WHERE ticker = 'LX' AND indicator_name = 'take_rate'"
        ).fetchone()
        assert row[0] is not None

    def test_update_returns_dict(self, store):
        """update_value should return updated record."""
        self._add_default(store)
        result = store.update_value("LX", "take_rate", 12.5, "2026Q2")
        assert isinstance(result, dict)
        assert result["latest_value"] == 12.5

    def test_update_nonexistent_raises(self, store):
        """Updating a nonexistent indicator should raise."""
        with pytest.raises(ValueError):
            store.update_value("LX", "nonexistent", 10.0, "2026Q2")


# ---------------------------------------------------------------------------
# test_status_calculation: automatic status from thresholds
# ---------------------------------------------------------------------------


class TestStatusCalculation:
    def _setup_indicator(self, store, threshold_pos=15.0, threshold_neg=8.0):
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="earnings", threshold_positive=threshold_pos,
            threshold_negative=threshold_neg, unit="%", category="revenue_quality",
        )

    def test_value_above_positive_threshold(self, store):
        """value >= threshold_positive → 'positive'."""
        self._setup_indicator(store)
        result = store.update_value("LX", "take_rate", 16.0, "2026Q2")
        assert result["status"] == "positive"

    def test_value_at_positive_threshold(self, store):
        """value == threshold_positive → 'positive'."""
        self._setup_indicator(store)
        result = store.update_value("LX", "take_rate", 15.0, "2026Q2")
        assert result["status"] == "positive"

    def test_value_below_negative_threshold(self, store):
        """value <= threshold_negative → 'negative'."""
        self._setup_indicator(store)
        result = store.update_value("LX", "take_rate", 7.0, "2026Q2")
        assert result["status"] == "negative"

    def test_value_at_negative_threshold(self, store):
        """value == threshold_negative → 'negative'."""
        self._setup_indicator(store)
        result = store.update_value("LX", "take_rate", 8.0, "2026Q2")
        assert result["status"] == "negative"

    def test_value_between_thresholds(self, store):
        """threshold_negative < value < threshold_positive → 'neutral'."""
        self._setup_indicator(store)
        result = store.update_value("LX", "take_rate", 12.0, "2026Q2")
        assert result["status"] == "neutral"

    def test_inverse_thresholds_lower_is_better(self, store):
        """When threshold_positive < threshold_negative, lower values are positive."""
        # e.g. debt_ratio: lower is better
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="debt_ratio",
            description="Debt ratio", source="financials", threshold_positive=30.0,
            threshold_negative=70.0, unit="%", category="financial_health",
        )
        # value=25 < threshold_positive=30 → positive
        result = store.update_value("LX", "debt_ratio", 25.0, "2026Q2")
        assert result["status"] == "positive"

        # value=75 > threshold_negative=70 → negative
        result = store.update_value("LX", "debt_ratio", 75.0, "2026Q2")
        assert result["status"] == "negative"

        # value=50 between → neutral
        result = store.update_value("LX", "debt_ratio", 50.0, "2026Q2")
        assert result["status"] == "neutral"


# ---------------------------------------------------------------------------
# test_get_indicators: retrieval
# ---------------------------------------------------------------------------


class TestGetIndicators:
    def _populate(self, store):
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="active_users",
            description="Active users", source="s", threshold_positive=1000000,
            threshold_negative=500000, unit="users", category="engagement",
        )
        store.add_indicator(
            ticker="MEDBOT", company_name="微创机器人", indicator_name="order_growth",
            description="Order growth", source="s", threshold_positive=30.0,
            threshold_negative=10.0, unit="%", category="growth",
        )

    def test_get_all(self, store):
        """No ticker filter → all indicators."""
        self._populate(store)
        results = store.get_indicators()
        assert len(results) == 3

    def test_filter_by_ticker(self, store):
        """Filtering by ticker returns only that ticker's indicators."""
        self._populate(store)
        results = store.get_indicators(ticker="LX")
        assert len(results) == 2
        assert all(r["ticker"] == "LX" for r in results)

    def test_returns_list_of_dicts(self, store):
        self._populate(store)
        results = store.get_indicators()
        assert isinstance(results, list)
        assert isinstance(results[0], dict)


# ---------------------------------------------------------------------------
# test_get_alerts: alerts for negative or missing-data indicators
# ---------------------------------------------------------------------------


class TestGetAlerts:
    def test_negative_status_alert(self, store):
        """Indicators with status='negative' should appear in alerts."""
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        store.update_value("LX", "take_rate", 5.0, "2026Q2")  # → negative
        alerts = store.get_alerts()
        assert len(alerts) >= 1
        assert any(a["indicator_name"] == "take_rate" for a in alerts)

    def test_no_data_alert(self, store):
        """Indicators with no latest_value should appear in alerts."""
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        alerts = store.get_alerts()
        assert len(alerts) >= 1
        assert any(a["indicator_name"] == "take_rate" for a in alerts)

    def test_positive_not_in_alerts(self, store):
        """Indicators with status='positive' should NOT appear in alerts."""
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        store.update_value("LX", "take_rate", 20.0, "2026Q2")  # → positive
        alerts = store.get_alerts()
        assert not any(a["indicator_name"] == "take_rate" for a in alerts)

    def test_neutral_not_in_alerts(self, store):
        """Indicators with status='neutral' should NOT appear in alerts."""
        store.add_indicator(
            ticker="LX", company_name="乐信", indicator_name="take_rate",
            description="Take rate", source="s", threshold_positive=15.0,
            threshold_negative=8.0, unit="%", category="revenue_quality",
        )
        store.update_value("LX", "take_rate", 12.0, "2026Q2")  # → neutral
        alerts = store.get_alerts()
        assert not any(a["indicator_name"] == "take_rate" for a in alerts)
