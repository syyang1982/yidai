"""
持仓实体 — 意怠工程 (Yidai)

决策(fill)不是学习单位。持仓(position)才是：一条论点、一组失效条件、
一个期限、若干买卖批次。决策记录通过 position_id 挂到持仓上。

设计原则：
- 同一 ticker 同时最多一个 open position
- 清仓后再买 = 新持仓（新 thesis）
- 卖出按 FIFO 消耗批次
- 历史补建允许 invalidation 为「待补全」；实盘开仓必须填写
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import duckdb


def default_decision_db() -> str:
    """Canonical store for decision_log + positions."""
    return os.path.join(
        os.path.expanduser("~"), ".hermes", "yidai", "db", "decisions.duckdb"
    )


@dataclass
class Lot:
    """One fill attached to a position."""

    decision_id: str = ""
    date: str = ""
    action: str = ""
    shares: int = 0
    price: float = 0.0


@dataclass
class Position:
    """A living investment thesis, not a single fill."""

    position_id: str = ""
    ticker: str = ""
    company_name: str = ""
    market: str = ""
    status: str = "open"          # open / closed
    book: str = "compound"        # compound (6-12m) / tactical (1w-1m)
    thesis: str = ""
    invalidation: str = ""
    horizon: str = "12m"          # 1w / 1m / 6m / 12m
    max_size_pct: float = 0.0
    currency: str = "HKD"
    shares: int = 0
    avg_cost: float = 0.0
    lots: List[Lot] = field(default_factory=list)
    opened_at: str = ""
    closed_at: str = ""
    close_reason: str = ""
    created_at: str = ""
    updated_at: str = ""

    def needs_invalidation(self) -> bool:
        text = (self.invalidation or "").strip()
        return text == "" or text == "待补全"


class PositionBook:
    """CRUD + FIFO fills for the positions table."""

    def __init__(self, db_path: str = None, conn=None):
        if conn is not None:
            self.conn = conn
            self.db_path = db_path or ""
        else:
            if db_path is None:
                db_path = ":memory:"
            self.db_path = db_path
            self.conn = duckdb.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                position_id VARCHAR PRIMARY KEY,
                ticker VARCHAR,
                company_name VARCHAR,
                market VARCHAR,
                status VARCHAR,
                book VARCHAR,
                thesis VARCHAR,
                invalidation VARCHAR,
                horizon VARCHAR,
                max_size_pct DOUBLE,
                currency VARCHAR,
                shares INTEGER,
                avg_cost DOUBLE,
                lots JSON,
                opened_at VARCHAR,
                closed_at VARCHAR,
                close_reason VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)

    def get(self, position_id: str) -> Optional[Position]:
        row = self.conn.execute(
            "SELECT * FROM positions WHERE position_id = ?",
            [position_id],
        ).fetchone()
        if not row:
            return None
        return self._row_to_position(row)

    def get_open(self, ticker: str) -> Optional[Position]:
        row = self.conn.execute(
            """SELECT * FROM positions
               WHERE ticker = ? AND status = 'open'
               ORDER BY opened_at DESC LIMIT 1""",
            [ticker],
        ).fetchone()
        if not row:
            return None
        return self._row_to_position(row)

    def list_open(self) -> List[Position]:
        rows = self.conn.execute(
            """SELECT * FROM positions WHERE status = 'open'
               ORDER BY ticker"""
        ).fetchall()
        return [self._row_to_position(r) for r in rows]

    def list_all(self, ticker: str = None, status: str = None) -> List[Position]:
        sql = "SELECT * FROM positions WHERE 1=1"
        params: list = []
        if ticker:
            sql += " AND ticker = ?"
            params.append(ticker)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY opened_at DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_position(r) for r in rows]

    def save(self, pos: Position) -> Position:
        now = datetime.now().isoformat()
        if not pos.position_id:
            pos.position_id = str(uuid.uuid4())[:8]
        if not pos.created_at:
            pos.created_at = now
        pos.updated_at = now
        lots_json = json.dumps(
            [lot.__dict__ for lot in pos.lots],
            ensure_ascii=False,
            default=str,
        )
        self.conn.execute(
            """
            INSERT OR REPLACE INTO positions (
                position_id, ticker, company_name, market, status, book,
                thesis, invalidation, horizon, max_size_pct, currency,
                shares, avg_cost, lots, opened_at, closed_at, close_reason,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                pos.position_id, pos.ticker, pos.company_name, pos.market,
                pos.status, pos.book, pos.thesis, pos.invalidation, pos.horizon,
                pos.max_size_pct, pos.currency, pos.shares, pos.avg_cost,
                lots_json, pos.opened_at, pos.closed_at, pos.close_reason,
                pos.created_at, pos.updated_at,
            ],
        )
        return pos

    def apply_fill(
        self,
        rec,
        book: str = "",
        invalidation: str = "",
        horizon: str = "",
        max_size_pct: float = 0.0,
        require_invalidation: bool = False,
    ) -> dict:
        """Attach a DecisionRecord to an open position (or open/close one).

        Returns {position, warnings, violations, accepted}.
        Does not write the decision itself.
        """
        warnings: list[str] = []
        violations: list[str] = []
        action = (rec.action or "").upper()
        ticker = rec.ticker
        raw_date = rec.decision_date or datetime.now().date().isoformat()
        now = str(raw_date)[:10]

        if action in ("BUY", "ADD"):
            pos = self.get_open(ticker)
            opened_new = False
            if pos is None:
                opened_new = True
                pos = Position(
                    ticker=ticker,
                    company_name=getattr(rec, "company_name", "") or ticker,
                    market=getattr(rec, "market", "") or "",
                    book=book or "compound",
                    thesis=getattr(rec, "thesis", "") or "",
                    invalidation=(invalidation or "").strip() or "待补全",
                    horizon=horizon or ("1m" if (book or "compound") == "tactical" else "12m"),
                    max_size_pct=max_size_pct or getattr(rec, "portfolio_pct", 0) or 0,
                    currency=getattr(rec, "currency", "") or "HKD",
                    opened_at=now,
                )
            else:
                if book:
                    pos.book = book
                if invalidation:
                    pos.invalidation = invalidation.strip()
                if horizon:
                    pos.horizon = horizon
                if max_size_pct:
                    pos.max_size_pct = max_size_pct
                if getattr(rec, "thesis", "") and not pos.thesis:
                    pos.thesis = rec.thesis

            if require_invalidation and pos.needs_invalidation():
                violations.append(
                    f"{ticker} 开仓/加仓必须填写失效条件 --invalidation "
                    "（什么情况无条件卖出，与盈亏无关）"
                )
                return {
                    "position": pos,
                    "warnings": warnings,
                    "violations": violations,
                    "accepted": False,
                }

            pos.lots.append(Lot(
                decision_id=getattr(rec, "decision_id", "") or "",
                date=now,
                action=action,
                shares=int(rec.shares or 0),
                price=float(rec.price or 0),
            ))
            self._recompute(pos)
            self.save(pos)
            rec.position_id = pos.position_id
            if opened_new:
                warnings.append(f"新持仓 {pos.position_id} {ticker} book={pos.book}")
            return {
                "position": pos,
                "warnings": warnings,
                "violations": violations,
                "accepted": True,
            }

        if action in ("SELL", "REDUCE"):
            pos = self.get_open(ticker)
            if pos is None:
                warnings.append(f"{ticker} 无 open position，卖出未入账到持仓")
                return {
                    "position": None,
                    "warnings": warnings,
                    "violations": violations,
                    "accepted": True,
                }
            sold = int(rec.shares or 0)
            if sold <= 0:
                warnings.append("卖出股数为 0，持仓未变")
                self.save(pos)
                rec.position_id = pos.position_id
                return {
                    "position": pos,
                    "warnings": warnings,
                    "violations": violations,
                    "accepted": True,
                }
            if sold > pos.shares:
                warnings.append(
                    f"卖出 {sold} > 持仓 {pos.shares}，按清仓处理"
                )
                sold = pos.shares
            self._consume_fifo(pos, sold)
            pos.lots.append(Lot(
                decision_id=getattr(rec, "decision_id", "") or "",
                date=now,
                action=action,
                shares=sold,
                price=float(rec.price or 0),
            ))
            # FIFO consume already reduced remaining buy lots; the sell lot
            # is an audit trail and must not count toward shares.
            self._recompute(pos, ignore_sell_lots=True)
            if pos.shares <= 0:
                pos.status = "closed"
                pos.closed_at = now
                pos.close_reason = getattr(rec, "sell_reason", "") or getattr(rec, "reason", "") or action
                pos.shares = 0
                pos.avg_cost = 0.0
            self.save(pos)
            rec.position_id = pos.position_id
            return {
                "position": pos,
                "warnings": warnings,
                "violations": violations,
                "accepted": True,
            }

        # HOLD or unknown: attach id if an open position exists
        pos = self.get_open(ticker)
        if pos:
            rec.position_id = pos.position_id
        return {
            "position": pos,
            "warnings": warnings,
            "violations": violations,
            "accepted": True,
        }

    def update_meta(
        self,
        ticker: str,
        thesis: str = None,
        invalidation: str = None,
        book: str = None,
        horizon: str = None,
        max_size_pct: float = None,
    ) -> Optional[Position]:
        pos = self.get_open(ticker)
        if pos is None:
            return None
        if thesis is not None:
            pos.thesis = thesis
        if invalidation is not None:
            pos.invalidation = invalidation
        if book is not None:
            pos.book = book
        if horizon is not None:
            pos.horizon = horizon
        if max_size_pct is not None:
            pos.max_size_pct = max_size_pct
        return self.save(pos)

    def rebuild_from_decisions(self, decision_log) -> dict:
        """Replay decision_log in date order. Historical gaps get 待补全."""
        recs = decision_log.list_decisions(limit=5000)
        recs = sorted(recs, key=lambda r: (r.decision_date or "", r.created_at or ""))
        opened = 0
        closed = 0
        attached = 0
        for rec in recs:
            result = self.apply_fill(rec, require_invalidation=False)
            if not result["accepted"]:
                continue
            pos = result["position"]
            if pos is None:
                continue
            attached += 1
            if rec.action in ("BUY", "ADD") and str(pos.opened_at)[:10] == str(rec.decision_date)[:10]:
                opened += 1
            if pos.status == "closed" and str(pos.closed_at)[:10] == str(rec.decision_date)[:10]:
                closed += 1
            rec.position_id = pos.position_id
            if rec.decision_id:
                decision_log.conn.execute(
                    "UPDATE decision_log SET position_id = ? WHERE decision_id = ?",
                    [pos.position_id, rec.decision_id],
                )
        return {
            "decisions": len(recs),
            "attached": attached,
            "open": len(self.list_open()),
            "all": len(self.list_all()),
        }

    def to_markdown(self, pos: Position) -> str:
        inv = pos.invalidation or "待补全"
        lines = [
            f"### {pos.company_name or pos.ticker} ({pos.ticker})  [{pos.status}]",
            f"- **position_id:** {pos.position_id}",
            f"- **账本:** {pos.book}  **期限:** {pos.horizon}",
            f"- **股数:** {pos.shares:,}  **均价:** {pos.avg_cost:.3f} {pos.currency}",
            f"- **论点:** {pos.thesis or '—'}",
            f"- **失效条件:** {inv}",
        ]
        if pos.max_size_pct:
            lines.append(f"- **仓位上限:** {pos.max_size_pct:.1f}%")
        if pos.opened_at:
            lines.append(f"- **开仓:** {pos.opened_at}")
        if pos.closed_at:
            lines.append(f"- **平仓:** {pos.closed_at} ({pos.close_reason})")
        buy_lots = [l for l in pos.lots if l.action in ("BUY", "ADD") and l.shares > 0]
        if buy_lots:
            lines.append("- **剩余批次:**")
            for lot in buy_lots:
                lines.append(
                    f"  - {lot.date} {lot.action} {lot.shares:,} @ {lot.price} "
                    f"[{lot.decision_id}]"
                )
        return "\n".join(lines)

    def _recompute(self, pos: Position, ignore_sell_lots: bool = False):
        remaining = [
            l for l in pos.lots
            if l.action in ("BUY", "ADD") and l.shares > 0
        ]
        pos.shares = sum(l.shares for l in remaining)
        if pos.shares > 0:
            pos.avg_cost = sum(l.shares * l.price for l in remaining) / pos.shares
        else:
            pos.avg_cost = 0.0

    def _consume_fifo(self, pos: Position, shares_to_sell: int):
        left = shares_to_sell
        for lot in pos.lots:
            if left <= 0:
                break
            if lot.action not in ("BUY", "ADD") or lot.shares <= 0:
                continue
            take = min(lot.shares, left)
            lot.shares -= take
            left -= take

    def _row_to_position(self, row) -> Position:
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM positions LIMIT 0"
        ).description]
        d = dict(zip(cols, row))
        lots_raw = d.get("lots") or "[]"
        if isinstance(lots_raw, str):
            try:
                lots_data = json.loads(lots_raw)
            except json.JSONDecodeError:
                lots_data = []
        elif isinstance(lots_raw, list):
            lots_data = lots_raw
        else:
            lots_data = []
        lots = [Lot(**{k: v for k, v in item.items() if k in Lot.__dataclass_fields__})
                for item in lots_data]
        pos = Position(lots=lots)
        for k, v in d.items():
            if k == "lots":
                continue
            if hasattr(pos, k) and v is not None:
                setattr(pos, k, v)
        return pos
