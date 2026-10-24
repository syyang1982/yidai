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
    dimension_map JSON,
    created_at VARCHAR,
    updated_at VARCHAR,
    PRIMARY KEY (ticker, indicator_name)
)
"""

_CREATE_HISTORY = """
CREATE TABLE IF NOT EXISTS indicator_history (
    ticker VARCHAR NOT NULL,
    indicator_name VARCHAR NOT NULL,
    period VARCHAR NOT NULL,
    value DOUBLE,
    status VARCHAR,
    recorded_date DATE,
    recorded_at VARCHAR,
    PRIMARY KEY (ticker, indicator_name, period)
)
"""

_COLUMNS = [
    "ticker", "company_name", "indicator_name", "description", "source",
    "threshold_positive", "threshold_negative", "unit", "category",
    "latest_value", "latest_period", "latest_date", "status",
    "notes", "dimension_map", "created_at", "updated_at",
]


def _row_to_dict(row: tuple) -> dict:
    """Convert a DuckDB row to a dict."""
    import json as _json
    d = dict(zip(_COLUMNS, row))
    # Parse dimension_map from JSON string to dict if needed
    dm = d.get("dimension_map")
    if isinstance(dm, str):
        try:
            d["dimension_map"] = _json.loads(dm)
        except (ValueError, TypeError):
            d["dimension_map"] = None
    return d


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
        """Create leading_indicators / indicator_history tables if they don't exist."""
        self.conn.execute(_CREATE_TABLE)
        self.conn.execute(_CREATE_HISTORY)
        # Migration: add dimension_map column to existing tables
        try:
            self.conn.execute(
                "ALTER TABLE leading_indicators ADD COLUMN IF NOT EXISTS dimension_map JSON"
            )
        except Exception:
            pass  # column already exists

    def record_history(
        self,
        ticker: str,
        indicator_name: str,
        period: str,
        value: float,
        status: Optional[str] = None,
    ) -> None:
        """按期写入指标历史值。同一期重复写入则覆盖（幂等）。

        「连续N期」判定必须靠这张表——leading_indicators 只存最新值。
        """
        row = self.conn.execute(
            "SELECT threshold_positive, threshold_negative FROM leading_indicators "
            "WHERE ticker = ? AND indicator_name = ?",
            [ticker, indicator_name],
        ).fetchone()
        if row is None:
            raise ValueError(
                f"Indicator '{indicator_name}' for ticker '{ticker}' not found. "
                "Call add_indicator() first."
            )
        if status is None:
            status = _calculate_status(value, row[0], row[1])
        now_date = date.today().isoformat()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            """
            INSERT INTO indicator_history
                (ticker, indicator_name, period, value, status, recorded_date, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, indicator_name, period) DO UPDATE SET
                value = excluded.value,
                status = excluded.status,
                recorded_date = excluded.recorded_date,
                recorded_at = excluded.recorded_at
            """,
            [ticker, indicator_name, period, float(value), status, now_date, now_ts],
        )

    def get_history(
        self,
        ticker: str,
        indicator_name: str,
        limit: int = 12,
    ) -> list[dict]:
        """按期倒序取历史值（最新在前）。"""
        rows = self.conn.execute(
            "SELECT period, value, status, recorded_date FROM indicator_history "
            "WHERE ticker = ? AND indicator_name = ? "
            "ORDER BY period DESC LIMIT ?",
            [ticker, indicator_name, limit],
        ).fetchall()
        return [
            {"period": r[0], "value": r[1], "status": r[2], "recorded_date": r[3]}
            for r in rows
        ]

    def consecutive_periods_negative(
        self,
        ticker: str,
        indicator_name: str,
        limit: int = 4,
    ) -> int:
        """从最新一期往前，连续为 negative 的期数。用于「连续两季下滑」判定。"""
        hist = self.get_history(ticker, indicator_name, limit=limit)
        n = 0
        for h in hist:
            if h["status"] == "negative":
                n += 1
            else:
                break
        return n

    def consecutive_periods_trending(
        self,
        ticker: str,
        indicator_name: str,
        direction: str,
        limit: int = 6,
    ) -> int:
        """从最新一期往前，连续朝 direction 方向变化的期数。

        direction="up"   数值连续上升的期数（如不良率 3.0→3.1→3.5→3.6 = 3）
        direction="down" 数值连续下降的期数

        用于「不良率连续两季上升」「定点数连续两季净减少」这类趋势条件——
        水平判定会漏掉它们：值还没到极端区间，但方向已经连续偏坏。
        等值（持平）不计入也不打断，避免小数抖动误判。
        """
        hist = self.get_history(ticker, indicator_name, limit=limit)
        vals = [h["value"] for h in hist if h.get("value") is not None]
        n = 0
        for prev, cur in zip(vals, vals[1:]):   # hist 是倒序（新→旧），所以 prev 更新
            if direction == "up":
                if cur < prev:
                    n += 1
                elif cur > prev:
                    break
            else:  # down
                if cur > prev:
                    n += 1
                elif cur < prev:
                    break
        return n

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
        dimension_map: dict | None = None,
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
            dimension_map: Optional dict mapping status to scorer dimension
                adjustments. E.g. {"negative": {"growth": -1}, "positive": {"growth": 0.5}}.

        Returns:
            The stored record as a dict.
        """
        import json as _json
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dm_json = _json.dumps(dimension_map) if dimension_map else None
        self.conn.execute(
            """
            INSERT INTO leading_indicators (
                ticker, company_name, indicator_name, description, source,
                threshold_positive, threshold_negative, unit, category,
                notes, dimension_map, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'neutral', ?, ?)
            ON CONFLICT (ticker, indicator_name) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                description = EXCLUDED.description,
                source = EXCLUDED.source,
                threshold_positive = EXCLUDED.threshold_positive,
                threshold_negative = EXCLUDED.threshold_negative,
                unit = EXCLUDED.unit,
                category = EXCLUDED.category,
                notes = EXCLUDED.notes,
                dimension_map = EXCLUDED.dimension_map,
                updated_at = EXCLUDED.updated_at
            """,
            [
                ticker, company_name, indicator_name, description, source,
                threshold_positive, threshold_negative, unit, category,
                notes, dm_json, now, now,
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
        # 同步写历史，否则「连续两季」判定无从做起（幂等，同周期覆盖）
        self.record_history(ticker, indicator_name, period, value, status)

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
