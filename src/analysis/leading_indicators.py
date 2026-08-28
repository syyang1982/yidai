"""Leading indicator structured tracking module.

Stores and tracks leading indicators for companies with automatic
status calculation based on configurable thresholds.

Status logic:
  - value >= threshold_positive → 'positive'
  - value <= threshold_negative → 'negative'
  - between thresholds         → 'neutral'

Supports both "higher is better" (threshold_positive > threshold_negative)
and "lower is better" (threshold_positive < threshold_negative) indicators.
"""

from __future__ import annotations

import os
from datetime import datetime, date
from typing import Optional

import duckdb

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "db", "leading_indicators.duckdb")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS leading_indicators (
    ticker VARCHAR NOT NULL,
    company_name VARCHAR,
    indicator_name VARCHAR NOT NULL,
    description VARCHAR,
    source VARCHAR,
    threshold_positive DOUBLE,
    threshold_negative DOUBLE,
    unit VARCHAR,
    category VARCHAR,
    latest_value DOUBLE,
    latest_period VARCHAR,
    latest_date DATE,
    status VARCHAR DEFAULT 'neutral',
    notes VARCHAR,
    created_at VARCHAR,
    updated_at VARCHAR,
    PRIMARY KEY (ticker, indicator_name)
)
"""

_COLUMNS = [
    "ticker", "company_name", "indicator_name", "description", "source",
    "threshold_positive", "threshold_negative", "unit", "category",
    "latest_value", "latest_period", "latest_date", "status",
    "notes", "created_at", "updated_at",
]


def _row_to_dict(row: tuple) -> dict:
    """Convert a DuckDB row to a dict."""
    return dict(zip(_COLUMNS, row))


def _calculate_status(
    value: float,
    threshold_positive: Optional[float],
    threshold_negative: Optional[float],
) -> str:
    """Calculate status from value and thresholds.

    Supports both 'higher is better' (pos > neg) and 'lower is better' (pos < neg).

    Returns: 'positive', 'negative', or 'neutral'.
    """
    if threshold_positive is None or threshold_negative is None:
        return "neutral"

    # "Higher is better": threshold_positive > threshold_negative
    if threshold_positive >= threshold_negative:
        if value >= threshold_positive:
            return "positive"
        if value <= threshold_negative:
            return "negative"
        return "neutral"
    else:
        # "Lower is better": threshold_positive < threshold_negative
        if value <= threshold_positive:
            return "positive"
        if value >= threshold_negative:
            return "negative"
        return "neutral"


class LeadingIndicatorStore:
    """DuckDB-backed store for structured leading indicator tracking."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize store and create tables if they don't exist.

        Args:
            db_path: Path to DuckDB database file. Defaults to db/leading_indicators.duckdb.
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self._create_tables()

    def _create_tables(self):
        """Create leading_indicators table if it does not exist."""
        self.conn.execute(_CREATE_TABLE)

    def add_indicator(
        self,
        ticker: str,
        company_name: str,
        indicator_name: str,
        description: str,
        source: str,
        threshold_positive: float,
        threshold_negative: float,
        unit: str,
        category: str,
        notes: str = "",
    ) -> dict:
        """Add or update a leading indicator definition.

        Args:
            ticker: Stock ticker (e.g. 'LX').
            company_name: Company name (e.g. '乐信').
            indicator_name: Unique indicator name within the ticker.
            description: Human-readable description.
            source: Data source (e.g. 'earnings_call', 'financials').
            threshold_positive: Value at/above which status is 'positive'.
            threshold_negative: Value at/below which status is 'negative'.
            unit: Unit of measurement (e.g. '%', 'users', 'ratio').
            category: Category grouping (e.g. 'revenue_quality', 'growth').
            notes: Optional notes.

        Returns:
            The stored record as a dict.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            """
            INSERT INTO leading_indicators (
                ticker, company_name, indicator_name, description, source,
                threshold_positive, threshold_negative, unit, category,
                notes, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'neutral', ?, ?)
            ON CONFLICT (ticker, indicator_name) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                description = EXCLUDED.description,
                source = EXCLUDED.source,
                threshold_positive = EXCLUDED.threshold_positive,
                threshold_negative = EXCLUDED.threshold_negative,
                unit = EXCLUDED.unit,
                category = EXCLUDED.category,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
            """,
            [
                ticker, company_name, indicator_name, description, source,
                threshold_positive, threshold_negative, unit, category,
                notes, now, now,
            ],
        )

        # Fetch and return the stored record
        row = self.conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM leading_indicators "
            "WHERE ticker = ? AND indicator_name = ?",
            [ticker, indicator_name],
        ).fetchone()
        return _row_to_dict(row)

    def update_value(
        self,
        ticker: str,
        indicator_name: str,
        value: float,
        period: str,
    ) -> dict:
        """Update the latest value for an indicator and auto-calculate status.

        Args:
            ticker: Stock ticker.
            indicator_name: Indicator name.
            value: New value.
            period: Period string (e.g. '2026Q2', '2026-07').

        Returns:
            The updated record as a dict.

        Raises:
            ValueError: If the indicator does not exist.
        """
        # Verify indicator exists and get thresholds
        existing = self.conn.execute(
            "SELECT threshold_positive, threshold_negative FROM leading_indicators "
            "WHERE ticker = ? AND indicator_name = ?",
            [ticker, indicator_name],
        ).fetchone()

        if existing is None:
            raise ValueError(
                f"Indicator '{indicator_name}' for ticker '{ticker}' not found. "
                "Call add_indicator() first."
            )

        threshold_pos, threshold_neg = existing
        status = _calculate_status(value, threshold_pos, threshold_neg)
        now_date = date.today().isoformat()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute(
            """
            UPDATE leading_indicators
            SET latest_value = ?,
                latest_period = ?,
                latest_date = ?,
                status = ?,
                updated_at = ?
            WHERE ticker = ? AND indicator_name = ?
            """,
            [value, period, now_date, status, now_ts, ticker, indicator_name],
        )

        # Return updated record
        row = self.conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM leading_indicators "
            "WHERE ticker = ? AND indicator_name = ?",
            [ticker, indicator_name],
        ).fetchone()
        return _row_to_dict(row)

    def get_indicators(self, ticker: Optional[str] = None) -> list[dict]:
        """Get indicator records, optionally filtered by ticker.

        Args:
            ticker: Optional ticker filter.

        Returns:
            List of indicator dicts.
        """
        if ticker:
            rows = self.conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM leading_indicators "
                "WHERE ticker = ? ORDER BY category, indicator_name",
                [ticker],
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM leading_indicators "
                "ORDER BY ticker, category, indicator_name"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_alerts(self) -> list[dict]:
        """Get indicators that need attention: negative status or no data.

        Returns:
            List of indicator dicts with status='negative' or latest_value IS NULL.
        """
        rows = self.conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM leading_indicators "
            "WHERE status = 'negative' OR latest_value IS NULL "
            "ORDER BY ticker, indicator_name"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def close(self):
        """Close the database connection."""
        self.conn.close()
