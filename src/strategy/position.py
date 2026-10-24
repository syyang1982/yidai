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


# ── 币种换算：持仓成本一律折算为持仓币种（港股=港币） ────────────────
# 口径来自 portfolio_config.DEFAULT_RATES，语义是「1 HKD 折多少该币种」，
# 所以 本币 → HKD 是除法。
try:
    from .portfolio_config import DEFAULT_RATES as _RATES
except Exception:  # pragma: no cover - 兜底，避免导入环
    _RATES = {"CNY_PER_HKD": 0.872489, "USD_PER_HKD": 0.1282, "AUD_PER_HKD": 0.17936}


def to_hkd(amount: float, currency: str) -> float:
    """任意币种 → HKD。未知/缺失币种按原值返回（不猜汇率）。"""
    if not currency or currency == "HKD":
        return float(amount)
    rate = _RATES.get(f"{currency}_PER_HKD")
    if not rate:
        return float(amount)
    return float(amount) / rate


def from_hkd(amount: float, currency: str) -> float:
    """HKD → 任意币种。"""
    if not currency or currency == "HKD":
        return float(amount)
    rate = _RATES.get(f"{currency}_PER_HKD")
    if not rate:
        return float(amount)
    return float(amount) * rate


def _norm_ticker(ticker: str) -> str:
    """对账/重放时的代码规范化：.ASX→.AX、去前导零、大写。"""
    t = (ticker or "").upper()
    if t.endswith(".ASX"):
        t = t[:-4] + ".AX"
    if "." in t:
        head, tail = t.split(".", 1)
        return head.lstrip("0") + "." + tail
    return t.lstrip("0")


def currency_for_ticker(ticker: str) -> str:
    """按市场推断持仓记账币种。口径：港股一律港币、A股人民币、ASX 澳元、美股美元。

    推断不出返回 ""（由调用方回退到成交币种）。"""
    t = (ticker or "").upper()
    if t.endswith(".HK"):
        return "HKD"
    if t.endswith((".SH", ".SZ", ".BJ")):
        return "CNY"
    if t.endswith((".AX", ".ASX")):
        return "AUD"
    if "." not in t:
        return "USD"
    return ""


@dataclass
class Lot:
    """One fill attached to a position."""

    decision_id: str = ""
    date: str = ""
    action: str = ""
    shares: int = 0
    price: float = 0.0
    currency: str = ""          # 成交币种；"" 视为与持仓币种相同


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
    reconciled_at: str = ""      # 非空 = 已按权威口径（券商/json）对账，rebuild 跳过
    reconciled_note: str = ""
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
                reconciled_at VARCHAR,
                reconciled_note VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        # 老库补列（幂等）
        existing = {r[1] for r in self.conn.execute(
            "PRAGMA table_info(positions)"
        ).fetchall()}
        for col in ("reconciled_at", "reconciled_note"):
            if col not in existing:
                self.conn.execute(f"ALTER TABLE positions ADD COLUMN {col} VARCHAR")

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
                reconciled_at, reconciled_note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                pos.position_id, pos.ticker, pos.company_name, pos.market,
                pos.status, pos.book, pos.thesis, pos.invalidation, pos.horizon,
                pos.max_size_pct, pos.currency, pos.shares, pos.avg_cost,
                lots_json, pos.opened_at, pos.closed_at, pos.close_reason,
                pos.reconciled_at, pos.reconciled_note, pos.created_at, pos.updated_at,
            ],
        )
        return pos

    @staticmethod
    def _lot_already_applied(pos, rec, action: str) -> bool:
        """该决策是否已入账（让 position rebuild 幂等，不重复累加 lot）。

        有 decision_id 时按 id 精确匹配；旧数据缺 id 时退回按
        日期+方向+股数+价格 匹配。"""
        did = getattr(rec, "decision_id", "") or ""
        rdate = str(getattr(rec, "decision_date", "") or "")[:10]
        rshares = int(getattr(rec, "shares", 0) or 0)
        rprice = float(getattr(rec, "price", 0) or 0)
        for lot in pos.lots:
            if did and lot.decision_id:
                if lot.decision_id == did and lot.action == action:
                    return True
                continue
            if (
                str(lot.date)[:10] == rdate
                and lot.action == action
                and lot.shares == rshares
                and abs(lot.price - rprice) < 1e-9
            ):
                return True
        return False

    def _find_replayed(self, rec, action: str):
        """在该 ticker 的所有持仓（含已平仓）里找已包含此决策的那条。"""
        rows = self.conn.execute(
            "SELECT * FROM positions WHERE ticker = ?",
            [getattr(rec, "ticker", "") or ""],
        ).fetchall()
        for row in rows:
            pos = self._row_to_position(row)
            if self._lot_already_applied(pos, rec, action):
                return pos
        return None

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
                # rebuild 重放已平仓持仓的买入时，复用原记录，避免每次 rebuild 都新增一条
                prior = self._find_replayed(rec, action)
                if prior is not None:
                    rec.position_id = prior.position_id
                    return {
                        "position": prior,
                        "warnings": warnings,
                        "violations": violations,
                        "accepted": True,
                    }
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
                    currency=currency_for_ticker(ticker) or getattr(rec, "currency", "") or "HKD",
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

            if self._lot_already_applied(pos, rec, action):
                # 重复回放（rebuild 幂等）：lot 已在仓，不再累加
                rec.position_id = pos.position_id
                return {
                    "position": pos,
                    "warnings": warnings,
                    "violations": violations,
                    "accepted": True,
                }

            pos.lots.append(Lot(
                decision_id=getattr(rec, "decision_id", "") or "",
                date=now,
                action=action,
                shares=int(rec.shares or 0),
                price=float(rec.price or 0),
                currency=getattr(rec, "currency", "") or "",
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
            if self._lot_already_applied(pos, rec, action):
                # 重复回放（rebuild 幂等）：卖出已入账，不再重复扣减
                rec.position_id = pos.position_id
                return {
                    "position": pos,
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
                currency=getattr(rec, "currency", "") or "",
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
        """Replay decision_log in date order. Historical gaps get 待补全.

        已对账持仓（reconciled_at 非空）跳过重放：其批次是券商/json 的权威口径，
        新成交在录入时已经通过 apply_fill 叠加过，再放一遍会翻倍。"""
        recs = decision_log.list_decisions(limit=5000)
        recs = sorted(recs, key=lambda r: (r.decision_date or "", r.created_at or ""))

        by_norm = {}
        for p in self.list_all():
            key = _norm_ticker(p.ticker)
            if key not in by_norm or p.status == "open":
                by_norm[key] = p
        reconciled = {k for k, p in by_norm.items() if p.reconciled_at}

        opened = 0
        closed = 0
        attached = 0
        skipped = 0
        for rec in recs:
            key = _norm_ticker(getattr(rec, "ticker", ""))
            if key in reconciled:
                skipped += 1
                pos = by_norm.get(key)
                if pos:
                    rec.position_id = pos.position_id
                    if rec.decision_id:
                        decision_log.conn.execute(
                            "UPDATE decision_log SET position_id = ? WHERE decision_id = ?",
                            [pos.position_id, rec.decision_id],
                        )
                continue
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
            "reconciled": len(reconciled),
            "skipped_reconciled": skipped,
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
        if pos.reconciled_at:
            lines.append(
                f"- **已对账:** {str(pos.reconciled_at)[:10]}（rebuild 跳过）"
                + (f"  {pos.reconciled_note}" if pos.reconciled_note else "")
            )
        buy_lots = [l for l in pos.lots if l.action in ("BUY", "ADD") and l.shares > 0]
        if buy_lots:
            lines.append("- **剩余批次:**")
            for lot in buy_lots:
                lines.append(
                    f"  - {lot.date} {lot.action} {lot.shares:,} @ {lot.price:.3f} "
                    f"{lot.currency or pos.currency} [{lot.decision_id or '对账批次'}]"
                )
        return "\n".join(lines)

    def _recompute(self, pos: Position, ignore_sell_lots: bool = False):
        remaining = [
            l for l in pos.lots
            if l.action in ("BUY", "ADD") and l.shares > 0
        ]
        pos.shares = sum(l.shares for l in remaining)
        if pos.shares > 0:
            # 成本一律折算为持仓币种（人民币/美元/澳元成交 → 港币，见 currency_for_ticker）
            cost_hkd = sum(l.shares * to_hkd(l.price, l.currency) for l in remaining)
            pos.avg_cost = from_hkd(cost_hkd / pos.shares, pos.currency)
        else:
            pos.avg_cost = 0.0

    def reconcile(self, ticker: str, lots, note: str = ""):
        """按权威口径（券商 / portfolio_data.json）直接写入持仓批次。

        lots: [(shares, price, currency), ...] 或 [{'shares','price','currency'}]。
        价格按原币种给出，内部折算为持仓币种（港股=港币）后落库。

        写入后 reconciled_at 非空 → rebuild_from_decisions 跳过该持仓，
        之后新增的成交仍通过 apply_fill 正常叠加。
        """
        pos = self.get_open(ticker)
        if pos is None:
            rows = self.list_all(ticker=ticker)
            pos = rows[0] if rows else None
        if pos is None:
            return None

        target = currency_for_ticker(ticker) or pos.currency or "HKD"
        pos.currency = target
        today = datetime.now().date().isoformat()
        new_lots: List[Lot] = []
        for item in lots:
            if isinstance(item, dict):
                shares = int(item.get("shares") or 0)
                price = float(item.get("price") or 0)
                ccy = item.get("currency") or target
            else:
                shares = int(item[0])
                price = float(item[1])
                ccy = (item[2] if len(item) > 2 else "") or target
            if shares <= 0:
                continue
            new_lots.append(Lot(
                decision_id="",
                date=today,
                action="BUY",
                shares=shares,
                price=from_hkd(to_hkd(price, ccy), target),
                currency=target,
            ))
        pos.lots = new_lots
        pos.reconciled_at = datetime.now().isoformat()
        pos.reconciled_note = note
        self._recompute(pos)
        return self.save(pos)

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
