"""DuckDB-backed event store for the 意怠工程 event engine."""

import os
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

import duckdb

from .models import MarketEvent

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "db", "events.duckdb")

_COLUMNS = [
    "event_id", "event_type", "title", "description",
    "event_date", "event_time", "affected_tickers", "sector",
    "source", "source_url", "impact_level", "impact_direction",
    "impact_analysis", "status", "notified", "created_at", "updated_at",
]

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS market_events (
    event_id VARCHAR PRIMARY KEY,
    event_type VARCHAR,
    title VARCHAR,
    description VARCHAR,
    event_date VARCHAR,
    event_time VARCHAR,
    affected_tickers VARCHAR,
    sector VARCHAR,
    source VARCHAR,
    source_url VARCHAR,
    impact_level VARCHAR,
    impact_direction VARCHAR,
    impact_analysis VARCHAR,
    status VARCHAR DEFAULT 'pending',
    notified BOOLEAN DEFAULT FALSE,
    created_at VARCHAR,
    updated_at VARCHAR
)
"""


def _row_to_event(row: tuple) -> MarketEvent:
    """Convert a DuckDB row tuple to a MarketEvent."""
    d = dict(zip(_COLUMNS, row))
    tickers_str = d["affected_tickers"] or ""
    d["affected_tickers"] = [t.strip() for t in tickers_str.split(",") if t.strip()]
    d["notified"] = bool(d["notified"])
    return MarketEvent(**d)


def _event_to_row(e: MarketEvent) -> tuple:
    """Convert a MarketEvent to a row tuple."""
    tickers_str = ",".join(e.affected_tickers)
    return (
        e.event_id, e.event_type, e.title, e.description,
        e.event_date, e.event_time, tickers_str, e.sector,
        e.source, e.source_url, e.impact_level, e.impact_direction,
        e.impact_analysis, e.status, e.notified, e.created_at, e.updated_at,
    )


class EventStore:
    """Manages market events in a DuckDB database."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self.conn.execute(_CREATE_TABLE)

    def close(self):
        self.conn.close()

    def add_event(self, event: MarketEvent) -> MarketEvent:
        """Add an event, auto-generating event_id if empty. Returns the event."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not event.event_id:
            event.event_id = str(uuid4())
        if not event.created_at:
            event.created_at = now
        event.updated_at = now
        self.conn.execute(
            f"INSERT INTO market_events ({', '.join(_COLUMNS)}) VALUES ({', '.join(['?']*len(_COLUMNS))})",
            _event_to_row(event),
        )
        return event

    def _query_events(self, where: str = "", params: list = None) -> List[MarketEvent]:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM market_events"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY event_date DESC, created_at DESC"
        rows = self.conn.execute(sql, params or []).fetchall()
        return [_row_to_event(r) for r in rows]

    def get_all(self) -> List[MarketEvent]:
        return self._query_events()

    def get_by_id(self, event_id: str) -> Optional[MarketEvent]:
        results = self._query_events("event_id = ?", [event_id])
        return results[0] if results else None

    def get_upcoming(self, days: int = 7, tickers: Optional[List[str]] = None) -> List[MarketEvent]:
        """Get upcoming events within N days, optionally filtered by tickers."""
        today = datetime.now().strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        conditions = ["event_date >= ?", "event_date <= ?"]
        params: list = [today, end]
        if tickers:
            ticker_conds = []
            for t in tickers:
                ticker_conds.append("affected_tickers LIKE ?")
                params.append(f"%{t}%")
            conditions.append(f"({' OR '.join(ticker_conds)})")
        return self._query_events(" AND ".join(conditions), params)

    def get_today(self) -> List[MarketEvent]:
        today = datetime.now().strftime("%Y-%m-%d")
        return self._query_events("event_date = ?", [today])

    def get_by_type(self, event_type: str) -> List[MarketEvent]:
        return self._query_events("event_type = ?", [event_type])

    def mark_notified(self, event_id: str) -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "UPDATE market_events SET notified = TRUE, updated_at = ? WHERE event_id = ?",
            [now, event_id],
        )
        # Verify the update took effect
        row = self.conn.execute(
            "SELECT notified FROM market_events WHERE event_id = ?", [event_id]
        ).fetchone()
        return row is not None and row[0]

    def update_impact(self, event_id: str, impact_level: str = "", impact_direction: str = "", impact_analysis: str = "") -> bool:
        sets, params = [], []
        if impact_level:
            sets.append("impact_level = ?")
            params.append(impact_level)
        if impact_direction:
            sets.append("impact_direction = ?")
            params.append(impact_direction)
        if impact_analysis:
            sets.append("impact_analysis = ?")
            params.append(impact_analysis)
        if not sets:
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sets.append("updated_at = ?")
        params.append(now)
        params.append(event_id)
        self.conn.execute(
            f"UPDATE market_events SET {', '.join(sets)} WHERE event_id = ?",
            params,
        )
        # Verify update took effect
        fetched = self.get_by_id(event_id)
        return fetched is not None

    def delete_event(self, event_id: str) -> bool:
        exists = self.get_by_id(event_id) is not None
        if not exists:
            return False
        self.conn.execute("DELETE FROM market_events WHERE event_id = ?", [event_id])
        return True
