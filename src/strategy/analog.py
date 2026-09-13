"""
决策时类比检索 — 意怠工程 (Yidai)

在写入 BUY/ADD 之前，把同类历史决策、该标的旧仓、以及知识库教训
摆到决策者面前。统计只按 playbook（reason_category + market）聚合，
不在个人样本上拟合 8 维权重。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AnalogMatch:
    decision_id: str
    ticker: str
    company_name: str
    action: str
    decision_date: str
    reason_category: str
    price: float
    actual_return_pct: float
    confidence_level: int
    lessons: str
    why: str


@dataclass
class AnalogReport:
    matches: List[AnalogMatch] = field(default_factory=list)
    playbook_n: int = 0
    playbook_reviewed: int = 0
    playbook_hit_rate: Optional[float] = None
    playbook_avg_return: Optional[float] = None
    confidence_n: int = 0
    confidence_hit_rate: Optional[float] = None
    lessons: List[dict] = field(default_factory=list)
    principles: List[dict] = field(default_factory=list)

    def format_text(self) -> str:
        lines = ["  📚 类比检索（写入前必读）"]
        cat = ""
        if self.matches:
            cat = self.matches[0].reason_category
        if self.playbook_n:
            hit = (
                f"{self.playbook_hit_rate*100:.0f}%"
                if self.playbook_hit_rate is not None else "样本不足"
            )
            avg = (
                f"{self.playbook_avg_return:+.1f}%"
                if self.playbook_avg_return is not None else "—"
            )
            lines.append(
                f"  玩法 {cat or '—'}: N={self.playbook_n} "
                f"已复盘 {self.playbook_reviewed}  胜率 {hit}  均收益 {avg}"
            )
        if self.confidence_n:
            chit = (
                f"{self.confidence_hit_rate*100:.0f}%"
                if self.confidence_hit_rate is not None else "—"
            )
            lines.append(
                f"  同信心水平历史: N={self.confidence_n}  胜率 {chit}"
            )
        if self.matches:
            lines.append("  相似决策:")
            for m in self.matches:
                ret = (
                    f"{m.actual_return_pct:+.1f}%"
                    if m.actual_return_pct else "未复盘"
                )
                name = m.company_name or m.ticker
                lines.append(
                    f"    - {m.decision_date} {name} ({m.ticker}) "
                    f"{m.action} @ {m.price}  {ret}  [{m.why}]"
                )
                if m.lessons:
                    lines.append(f"      教训: {m.lessons}")
        else:
            lines.append("  无足够相似历史（这是新玩法，缩小仓位）")
        if self.lessons:
            lines.append("  相关教训:")
            for lesson in self.lessons[:3]:
                lines.append(f"    - {lesson.get('content', '')}")
        if self.principles:
            lines.append("  相关原则:")
            for p in self.principles[:3]:
                lines.append(f"    - {p.get('principle', '')}")
        return "\n".join(lines)


def _hit(rec) -> Optional[bool]:
    if rec.actual_return_pct == 0 and not (rec.actual_price_6m or rec.actual_price_12m):
        return None
    if rec.action in ("SELL", "REDUCE"):
        return rec.actual_return_pct >= 0
    return rec.actual_return_pct > 0


def find_analogs(decision_log, rec, knowledge_base=None, limit: int = 4) -> AnalogReport:
    """Retrieve comparable past decisions for a pending record."""
    report = AnalogReport()
    all_recs = decision_log.list_decisions(limit=2000)
    pending_id = getattr(rec, "decision_id", "") or ""
    category = getattr(rec, "reason_category", "") or ""
    market = getattr(rec, "market", "") or ""
    ticker = getattr(rec, "ticker", "") or ""
    confidence = int(getattr(rec, "confidence_level", 0) or 0)

    def is_self(r) -> bool:
        return pending_id and r.decision_id == pending_id

    # Playbook: same reason_category (+ market if known)
    playbook = [
        r for r in all_recs
        if not is_self(r)
        and category
        and r.reason_category == category
        and (not market or r.market == market or not r.market)
    ]
    report.playbook_n = len(playbook)
    reviewed = [r for r in playbook if _hit(r) is not None]
    report.playbook_reviewed = len(reviewed)
    if reviewed:
        hits = [r for r in reviewed if _hit(r)]
        report.playbook_hit_rate = len(hits) / len(reviewed)
        report.playbook_avg_return = sum(r.actual_return_pct for r in reviewed) / len(reviewed)

    if confidence:
        same_conf = [
            r for r in all_recs
            if not is_self(r) and r.confidence_level == confidence and _hit(r) is not None
        ]
        report.confidence_n = len(same_conf)
        if same_conf:
            report.confidence_hit_rate = (
                sum(1 for r in same_conf if _hit(r)) / len(same_conf)
            )

    matches: List[AnalogMatch] = []
    # 1) same ticker first
    for r in all_recs:
        if is_self(r) or r.ticker != ticker:
            continue
        matches.append(_to_match(r, "同标的"))
    # 2) same playbook
    for r in playbook:
        if r.ticker == ticker:
            continue
        matches.append(_to_match(r, f"同玩法:{category}"))
        if len(matches) >= limit * 2:
            break

    # de-dup by decision_id, keep order, cap
    seen = set()
    uniq = []
    for m in matches:
        if m.decision_id in seen:
            continue
        seen.add(m.decision_id)
        uniq.append(m)
        if len(uniq) >= limit:
            break
    report.matches = uniq

    if knowledge_base is not None:
        try:
            lessons = knowledge_base.get_lessons() or []
            report.lessons = [
                L for L in lessons
                if (ticker and ticker in (L.get("source") or ""))
                or (category and category in ((L.get("category") or "") + (L.get("content") or "")))
            ][:5]
        except Exception:
            report.lessons = []
        try:
            report.principles = (knowledge_base.get_principles() or [])[:3]
        except Exception:
            report.principles = []

    return report


def _to_match(r, why: str) -> AnalogMatch:
    return AnalogMatch(
        decision_id=r.decision_id,
        ticker=r.ticker,
        company_name=r.company_name,
        action=r.action,
        decision_date=str(r.decision_date),
        reason_category=r.reason_category or "",
        price=float(r.price or 0),
        actual_return_pct=float(r.actual_return_pct or 0),
        confidence_level=int(r.confidence_level or 0),
        lessons=r.lessons or "",
        why=why,
    )
