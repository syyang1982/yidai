"""
决策日志系统 — 意怠工程 (Yidai)

记录每笔投资决策的完整上下文，为后续复盘闭环提供数据基础。

设计原则：
- 以人的决策为中心（区别于 signal_tracker 以系统信号为中心）
- 每笔决策快照当时的七维评分，用于后续验证哪些维度有预测力
- 支持关联到 signal_records（如果决策是基于系统信号做出的）
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import duckdb


@dataclass
class DecisionRecord:
    """一条投资决策的完整记录。"""

    decision_id: str = ""

    # 标的
    ticker: str = ""              # e.g. "01810.HK"
    company_name: str = ""        # e.g. "小米集团"
    market: str = ""              # "HK" / "A" / "US"

    # 决策内容
    action: str = ""              # "BUY" / "SELL" / "REDUCE" / "ADD" / "HOLD"
    shares: int = 0               # 交易股数（HOLD 时为 0）
    price: float = 0.0            # 交易价格（HOLD 时为当前价格）
    amount: float = 0.0           # 交易金额 = shares * price
    currency: str = "HKD"         # 交易货币

    # 决策理由
    reason: str = ""              # 简短理由（一句话）
    thesis: str = ""              # 完整投资论点
    catalyst: str = ""            # 催化剂 / 触发因素
    risk_note: str = ""           # 风险提示

    # 决策时的状态快照
    dimension_scores: dict = field(default_factory=dict)
    # {"盈利": 4, "健康": 3, "现金流": 4, "估值": 3, "成长": 5, "股东": 3, "战略": 4}
    total_score: int = 0
    grade: str = ""               # "A" / "B" / "C" / "D" / "F"
    signal: str = ""              # 系统当时的信号: "BUY" / "HOLD" / "WATCH" / "REDUCE"

    # 关联
    signal_id: str = ""           # 关联的 signal_records.signal_id（可空）
    portfolio_pct: float = 0.0    # 该笔交易后，此标的占总持仓的百分比

    # 预期
    expected_price_6m: float = 0.0   # 6个月后预期价格
    expected_price_12m: float = 0.0  # 12个月后预期价格
    expected_reasoning: str = ""     # 预期逻辑

    # 实际结果（后续填写）
    actual_price_6m: float = 0.0
    actual_price_12m: float = 0.0
    actual_return_pct: float = 0.0   # 实际收益率
    review_notes: str = ""           # 复盘笔记
    lessons: str = ""                # 经验教训

    # 元数据
    decision_date: str = ""       # 决策日期（用户指定）
    status: str = "active"        # "active" / "reviewed_6m" / "reviewed_12m" / "closed"
    created_at: str = ""
    updated_at: str = ""


class DecisionLog:
    """决策日志管理器。"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = ":memory:"
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_log (
                decision_id VARCHAR PRIMARY KEY,
                ticker VARCHAR,
                company_name VARCHAR,
                market VARCHAR,
                action VARCHAR,
                shares INTEGER,
                price DOUBLE,
                amount DOUBLE,
                currency VARCHAR,
                reason VARCHAR,
                thesis VARCHAR,
                catalyst VARCHAR,
                risk_note VARCHAR,
                dimension_scores JSON,
                total_score INTEGER,
                grade VARCHAR,
                signal VARCHAR,
                signal_id VARCHAR,
                portfolio_pct DOUBLE,
                expected_price_6m DOUBLE,
                expected_price_12m DOUBLE,
                expected_reasoning VARCHAR,
                actual_price_6m DOUBLE,
                actual_price_12m DOUBLE,
                actual_return_pct DOUBLE,
                review_notes VARCHAR,
                lessons VARCHAR,
                decision_date DATE,
                status VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)

    def _check_constraints(self, rec: DecisionRecord) -> tuple[list, list]:
        """返回 (warnings, violations)。warnings=软违规(仍记录), violations=硬违规(enforce时拒绝)。"""
        warnings: list[str] = []
        violations: list[str] = []

        # 1. 单股仓位上限
        if rec.portfolio_pct > 30:
            violations.append(f"单股仓位 {rec.portfolio_pct:.1f}% > 30% 硬上限")
        elif rec.portfolio_pct > 25:
            warnings.append(f"单股仓位 {rec.portfolio_pct:.1f}% > 25% 软上限")

        # 2. 连续买入同一标的检查(7天内重复买入)
        if rec.action in ("BUY", "ADD") and rec.ticker:
            date_val = rec.decision_date or date.today().isoformat()
            try:
                cutoff = (date.fromisoformat(date_val) - timedelta(days=7)).isoformat()
            except ValueError:
                cutoff = (date.today() - timedelta(days=7)).isoformat()
            recent = self.conn.execute(
                """SELECT COUNT(*) FROM decision_log
                   WHERE ticker = ? AND action IN ('BUY', 'ADD')
                   AND decision_date >= ?""",
                [rec.ticker, cutoff],
            ).fetchone()
            if recent and recent[0] >= 3:
                warnings.append(
                    f"7天内第{recent[0]+1}次买入{rec.ticker}，注意过度交易"
                )

        return warnings, violations

    def record(
        self, rec: DecisionRecord, enforce_constraints: bool = True
    ) -> dict:
        """记录一条决策。返回 {decision_id, warnings, violations, accepted}。

        Args:
            rec: DecisionRecord
            enforce_constraints: if True, reject if hard constraints violated

        Returns:
            dict with:
                - decision_id: str (empty if rejected)
                - warnings: list of str (soft violations, still recorded)
                - violations: list of str (hard violations, rejected if enforce)
                - accepted: bool
        """
        warnings, violations = self._check_constraints(rec)

        if enforce_constraints and violations:
            return {
                "decision_id": "",
                "warnings": warnings,
                "violations": violations,
                "accepted": False,
            }

        now = datetime.now().isoformat()
        if not rec.decision_id:
            rec.decision_id = str(uuid.uuid4())[:8]
        if not rec.created_at:
            rec.created_at = now
        rec.updated_at = now
        if not rec.decision_date:
            rec.decision_date = date.today().isoformat()
        if rec.shares and rec.price and not rec.amount:
            rec.amount = rec.shares * rec.price

        self.conn.execute(
            """
            INSERT OR REPLACE INTO decision_log VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                rec.decision_id, rec.ticker, rec.company_name, rec.market,
                rec.action, rec.shares, rec.price, rec.amount, rec.currency,
                rec.reason, rec.thesis, rec.catalyst, rec.risk_note,
                json.dumps(rec.dimension_scores, ensure_ascii=False),
                rec.total_score, rec.grade, rec.signal, rec.signal_id,
                rec.portfolio_pct,
                rec.expected_price_6m, rec.expected_price_12m, rec.expected_reasoning,
                rec.actual_price_6m, rec.actual_price_12m, rec.actual_return_pct,
                rec.review_notes, rec.lessons,
                rec.decision_date, rec.status,
                rec.created_at, rec.updated_at,
            ],
        )
        return {
            "decision_id": rec.decision_id,
            "warnings": warnings,
            "violations": violations,
            "accepted": True,
        }

    def get(self, decision_id: str) -> Optional[DecisionRecord]:
        """获取单条决策记录。"""
        row = self.conn.execute(
            'SELECT * FROM decision_log WHERE decision_id = ?',
            [decision_id],
        ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_decisions(
        self,
        ticker: str = None,
        action: str = None,
        status: str = None,
        limit: int = 50,
    ) -> List[DecisionRecord]:
        """列出决策记录，支持过滤。"""
        sql = "SELECT * FROM decision_log WHERE 1=1"
        params = []
        if ticker:
            sql += " AND ticker = ?"
            params.append(ticker)
        if action:
            sql += " AND action = ?"
            params.append(action)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY decision_date DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def record_outcome(
        self,
        decision_id: str,
        actual_price: float,
        period: str = "6m",
        review_notes: str = "",
        lessons: str = "",
    ) -> bool:
        """记录实际结果。period='6m' or '12m'。"""
        rec = self.get(decision_id)
        if not rec:
            return False

        now = datetime.now().isoformat()
        if period == "6m":
            self.conn.execute(
                """UPDATE decision_log SET
                    actual_price_6m = ?, review_notes = ?,
                    status = 'reviewed_6m', updated_at = ?
                WHERE decision_id = ?""",
                [actual_price, review_notes, now, decision_id],
            )
        else:
            # 计算收益率
            ret_pct = 0.0
            if rec.price > 0:
                ret_pct = (actual_price - rec.price) / rec.price * 100
            self.conn.execute(
                """UPDATE decision_log SET
                    actual_price_12m = ?, actual_return_pct = ?,
                    review_notes = ?, lessons = ?,
                    status = 'reviewed_12m', updated_at = ?
                WHERE decision_id = ?""",
                [actual_price, ret_pct, review_notes, lessons, now, decision_id],
            )
        return True

    def get_pending_reviews(self, period: str = "6m") -> List[DecisionRecord]:
        """获取需要复盘的决策。"""
        if period == "6m":
            rows = self.conn.execute(
                """SELECT * FROM decision_log
                   WHERE status = 'active'
                   AND decision_date <= CURRENT_DATE - INTERVAL '6 months'
                   ORDER BY decision_date""",
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM decision_log
                   WHERE status = 'reviewed_6m'
                   AND decision_date <= CURRENT_DATE - INTERVAL '12 months'
                   ORDER BY decision_date""",
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_stats(self) -> dict:
        """汇总统计。"""
        total = self.conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
        by_action = self.conn.execute(
            "SELECT action, COUNT(*) FROM decision_log GROUP BY action"
        ).fetchall()
        reviewed = self.conn.execute(
            "SELECT COUNT(*) FROM decision_log WHERE status LIKE 'reviewed%'"
        ).fetchone()[0]
        avg_return = self.conn.execute(
            "SELECT AVG(actual_return_pct) FROM decision_log WHERE actual_return_pct != 0"
        ).fetchone()[0]

        return {
            "total_decisions": total,
            "by_action": {r[0]: r[1] for r in by_action},
            "reviewed": reviewed,
            "pending_review": total - reviewed,
            "avg_return_pct": round(avg_return, 2) if avg_return else 0,
        }

    def _row_to_record(self, row) -> DecisionRecord:
        """将数据库行转换为 DecisionRecord。"""
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM decision_log LIMIT 0"
        ).description]
        d = dict(zip(cols, row))
        rec = DecisionRecord()
        for k, v in d.items():
            if k == "dimension_scores" and isinstance(v, str):
                setattr(rec, k, json.loads(v))
            elif hasattr(rec, k):
                setattr(rec, k, v)
        return rec

    def to_markdown(self, rec: DecisionRecord) -> str:
        """将决策记录格式化为 Markdown。"""
        scores_str = ""
        if rec.dimension_scores:
            parts = [f"{k}:{v}" for k, v in rec.dimension_scores.items()]
            scores_str = " | ".join(parts)

        lines = [
            f"### {rec.decision_date} — {rec.company_name} ({rec.ticker})",
            f"- **操作:** {rec.action} {rec.shares}股 @ {rec.price} {rec.currency}",
            f"- **金额:** {rec.amount:,.0f} {rec.currency}",
            f"- **理由:** {rec.reason}",
        ]
        if rec.thesis:
            lines.append(f"- **论点:** {rec.thesis}")
        if rec.catalyst:
            lines.append(f"- **催化剂:** {rec.catalyst}")
        if rec.risk_note:
            lines.append(f"- **风险:** {rec.risk_note}")
        lines.append(f"- **评分:** {rec.total_score}/40 ({rec.grade}, 信号:{rec.signal})")
        if scores_str:
            lines.append(f"  - {scores_str}")
        if rec.portfolio_pct > 0:
            lines.append(f"- **持仓占比:** {rec.portfolio_pct:.1f}%")
        if rec.expected_price_6m > 0:
            lines.append(f"- **6M预期:** {rec.expected_price_6m} {rec.currency}")
        if rec.expected_price_12m > 0:
            lines.append(f"- **12M预期:** {rec.expected_price_12m} {rec.currency}")
        if rec.expected_reasoning:
            lines.append(f"- **预期逻辑:** {rec.expected_reasoning}")
        if rec.status.startswith("reviewed"):
            lines.append(f"- **状态:** {rec.status}")
            if rec.actual_price_6m > 0:
                lines.append(f"- **6M实际:** {rec.actual_price_6m} {rec.currency}")
            if rec.actual_price_12m > 0:
                lines.append(f"- **12M实际:** {rec.actual_price_12m} {rec.currency}")
            if rec.actual_return_pct != 0:
                lines.append(f"- **收益率:** {rec.actual_return_pct:+.1f}%")
            if rec.review_notes:
                lines.append(f"- **复盘:** {rec.review_notes}")
            if rec.lessons:
                lines.append(f"- **教训:** {rec.lessons}")

        return "\n".join(lines)
