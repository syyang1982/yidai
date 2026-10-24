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

    @staticmethod
    def _dedup_key(event: MarketEvent) -> str:
        """事件业务唯一键: 同 类型+标题+日期+来源 视为同一条事件。"""
        return "||".join([
            (event.event_type or "").strip(),
            (event.title or "").strip(),
            (event.event_date or "").strip(),
            (event.source or "").strip(),
        ])

    def event_exists(self, event: MarketEvent) -> bool:
        """按业务唯一键判断事件是否已存在。"""
        row = self.conn.execute(
            "SELECT 1 FROM market_events WHERE event_type = ? AND title = ? "
            "AND event_date = ? AND coalesce(source,'') = ? LIMIT 1",
            [event.event_type, event.title, event.event_date, event.source or ""],
        ).fetchone()
        return row is not None

    def add_event(self, event: MarketEvent, dedup: bool = True) -> Optional[MarketEvent]:
        """添加事件。dedup=True 时若同业务键已存在则跳过，返回 None。

        这是 E1 重复写入的根因修复：--refresh 每次都调 add_event，
        过去无条件 INSERT 导致 34 条事件被写入 41 份拷贝。
        """
        if dedup and self.event_exists(event):
            return None
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

    def add_events(self, events: List[MarketEvent], dedup: bool = True) -> List[MarketEvent]:
        """批量添加，返回真正写入的事件。"""
        inserted = []
        for e in events:
            if self.add_event(e, dedup=dedup) is not None:
                inserted.append(e)
        return inserted

    def dedupe(self) -> int:
        """清理历史重复行：按业务唯一键保留最新一条，删除其余。返回删除数。"""
        before = self.conn.execute("SELECT count(*) FROM market_events").fetchone()
        before_n = int(before[0]) if before else 0
        self.conn.execute(
            """
            DELETE FROM market_events
            WHERE event_id NOT IN (
                SELECT arg_max(event_id, coalesce(updated_at,'') || '|' || coalesce(created_at,''))
                FROM market_events
                GROUP BY event_type, title, event_date, coalesce(source,'')
            )
            """
        )
        after = self.conn.execute("SELECT count(*) FROM market_events").fetchone()
        after_n = int(after[0]) if after else 0
        return max(0, before_n - after_n)

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

    def get_by_type(self, event_type: str, days: Optional[int] = None) -> List[MarketEvent]:
        """按类型查询事件。days 给定时只返回未来 N 天内（E3 修复：manage.py 传了 days 参数）。"""
        if days is None:
            return self._query_events("event_type = ?", [event_type])
        today = datetime.now().strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        return self._query_events(
            "event_type = ? AND event_date >= ? AND event_date <= ?",
            [event_type, today, end],
        )

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
