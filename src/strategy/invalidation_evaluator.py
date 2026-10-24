"""失效评估器 — 回答「这期失效腿是绿/黄/红，以及是否已触发失效」。

与 invalidation_watch.format_watch 的分工：
  format_watch 只读写入时算好的 status 做展示；
  本模块读 indicator_history 做「连续 N 期」判定并给出触发结论。

规则：
  - 单期红 = 进入危险区，不等于失效。
  - 写了「连续两季 / 两期 / 三个月」的腿，须连着红够期数才算触发。
  - 无历史记录的腿判 unknown —— 不得用空值判失效。

两种判定方式（2026-10-14 补）：
  - **水平判定**：腿写「跌破20%」「OCF仍负」这类绝对值条件 → 看 status 是否连续为红。
  - **趋势判定**：腿写「连续两季上升」「连续两季净减少」这类方向条件 → 看数值是否
    连续 N 期朝坏方向走。水平判定在这里会漏判：LX 不良率 3.6% 尚未到极端水平，
    但已连升 3 季，正是用户写的失效条件。两种判定任一满足即触发。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from src.analysis.leading_indicators import LeadingIndicatorStore
from src.strategy.invalidation_watch import WATCH

# 腿文本里的方向词 → 朝哪个方向算「变坏」
# 「不良率连续两季上升」→ 上升是坏（up）；「定点数连续两季净减少」→ 减少是坏（down）
_RISING_BAD = ("上升", "增加", "走高", "上行", "扩大", "创新高", "走强")
_FALLING_BAD = ("下滑", "下降", "减少", "走低", "收缩", "回落", "萎缩", "转负", "收窄",
                "负增长", "净减少", "转弱", "不达", "退坡", "恶化", "减速", "丢失", "变慢")


def trend_bad_direction(leg_text: str) -> Optional[str]:
    """从失效腿文本提取「往哪个方向走算坏」。

    返回 "up"（上升是坏）/ "down"（下降是坏）/ None（非趋势腿，走水平判定）。
    """
    if not leg_text:
        return None
    for kw in _RISING_BAD:
        if kw in leg_text:
            return "up"
    for kw in _FALLING_BAD:
        if kw in leg_text:
            return "down"
    return None


@dataclass
class LegEvaluation:
    ticker: str
    company_name: str
    indicator_name: str
    leg: str                    # 对应哪条失效腿
    consecutive: str            # "1期" / "2季" / "3个月"
    required_periods: int       # 需要连红几期
    value: Optional[float]
    unit: str
    period: str
    status: str                 # positive / neutral / negative / unknown
    red_streak: int             # 连续红了几期（水平判定）
    triggered: bool             # 是否达到失效判定
    history: list = field(default_factory=list)
    trend_direction: Optional[str] = None   # "up"/"down"/None
    trend_streak: int = 0                   # 连续朝坏方向几期
    judged_by: str = "level"                # "level" / "trend" / "none"

    @property
    def icon(self) -> str:
        if self.triggered:
            return "🚨"
        return {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}.get(self.status, "❓")

    @property
    def streak(self) -> int:
        """用于展示的「连续几期」——趋势腿看趋势，水平腿看红灯。"""
        return self.trend_streak if self.judged_by == "trend" else self.red_streak


def required_periods_from(consecutive: str) -> int:
    """把「2季」「3个月」「1期」翻译成需要连红几期。"""
    if not consecutive:
        return 1
    m = re.search(r"(\d+)", consecutive)
    return int(m.group(1)) if m else 1


def evaluate_ticker(
    store: LeadingIndicatorStore,
    ticker: str,
    company_name: str = "",
    specs: Optional[list] = None,
) -> list[LegEvaluation]:
    """评估单个持仓的失效腿。

    specs 传 WatchSpec 列表则用传入的（便于测试、以及监控 WATCH 表外的新持仓）；
    不传则从 WATCH 表按 ticker 取。
    """
    out: list[LegEvaluation] = []
    if specs is None:
        specs = [s for t, _, ss in WATCH if t == ticker for s in ss]
    rows = {r.get("indicator_name"): r for r in store.get_indicators(ticker)}
    for spec in specs:
        row = rows.get(spec.name) or {}
        value = row.get("latest_value")
        status = row.get("status") or "unknown"
        if value is None:
            status = "unknown"
        required = required_periods_from(spec.consecutive)
        limit = max(required, 6)

        # 趋势腿：腿文本含方向词（「连续两季上升/下滑」），按变化方向判定
        bad_dir = trend_bad_direction(spec.invalidation_leg)
        trend_streak = 0
        if bad_dir and required > 1:
            trend_streak = store.consecutive_periods_trending(
                ticker, spec.name, bad_dir, limit=limit
            )

        # 水平腿：连续红灯判定
        red_streak = store.consecutive_periods_negative(ticker, spec.name, limit=limit)

        # 触发：任一判定满足即算
        trend_hit = bad_dir is not None and required > 1 and trend_streak >= required
        level_hit = required > 1 and red_streak >= required
        triggered = trend_hit or level_hit

        if trend_hit:
            judged_by = "trend"
        elif level_hit:
            judged_by = "level"
        elif bad_dir is not None and required > 1:
            judged_by = "trend"
        else:
            judged_by = "level"

        # 触发时强制标红：水平上还没到极端值不代表没事（LX 不良率 3.6% 就是这样）
        if triggered and status not in ("unknown",):
            status = "negative"

        out.append(LegEvaluation(
            ticker=ticker,
            company_name=company_name,
            indicator_name=spec.name,
            leg=spec.invalidation_leg,
            consecutive=spec.consecutive,
            required_periods=required,
            value=value,
            unit=spec.unit,
            period=row.get("latest_period") or "",
            status=status,
            red_streak=red_streak,
            triggered=triggered,
            history=store.get_history(ticker, spec.name, limit=4),
            trend_direction=bad_dir,
            trend_streak=trend_streak,
            judged_by=judged_by,
        ))
    return out


def evaluate_all(store: LeadingIndicatorStore, positions) -> list[LegEvaluation]:
    """positions: iterable with .ticker and .company_name"""
    out: list[LegEvaluation] = []
    for p in positions:
        out.extend(evaluate_ticker(store, p.ticker, getattr(p, "company_name", "") or ""))
    return out


def summarize(evals: list[LegEvaluation]) -> dict:
    return {
        "total": len(evals),
        "triggered": sum(1 for e in evals if e.triggered),
        "red": sum(1 for e in evals if e.status == "negative"),
        "neutral": sum(1 for e in evals if e.status == "neutral"),
        "positive": sum(1 for e in evals if e.status == "positive"),
        "unknown": sum(1 for e in evals if e.status == "unknown"),
        "tickers": len({e.ticker for e in evals}),
    }


def format_report(evals: list[LegEvaluation], positions=None, show_all: bool = False) -> str:
    """渲染中文报告。默认只详列有红灯/触发/未知的仓，全绿的压成一行。"""
    icon_pos = {p.ticker: p for p in (positions or [])}
    lines: list[str] = []
    by_ticker: dict[str, list[LegEvaluation]] = {}
    for e in evals:
        by_ticker.setdefault(e.ticker, []).append(e)

    triggered = [e for e in evals if e.triggered]
    reds = [e for e in evals if e.status == "negative" and not e.triggered]
    unknowns = [e for e in evals if e.status == "unknown"]

    def streak_phrase(e: LegEvaluation) -> str:
        """按腿的判定方式说明「连续几期」——趋势腿说方向，水平腿说红灯。"""
        if e.judged_by == "trend":
            arrow = "↑上升" if e.trend_direction == "up" else "↓下降"
            return f"已连续 {e.trend_streak} 期{arrow}（需 {e.required_periods} 期）"
        return f"已连红 {e.red_streak} 期（需 {e.required_periods}）"

    if triggered:
        lines.append("🚨 失效条件已触发（需人工确认是否清仓）")
        for e in triggered:
            lines.append(f"  {e.ticker} {e.company_name} — {e.leg}")
            lines.append(
                f"     {e.indicator_name}: {e.value}{e.unit} [{e.period}] "
                f"{streak_phrase(e)}"
            )
        lines.append("")

    if reds:
        lines.append("🔴 单期红灯（进入危险区，尚未构成失效）")
        for e in reds:
            lines.append(f"  {e.ticker} {e.company_name} — {e.indicator_name}: {e.value}{e.unit} [{e.period}]")
            lines.append(f"     失效腿: {e.leg}（判定 {e.consecutive}）")
            if e.judged_by == "trend" and e.trend_streak:
                arrow = "↑上升" if e.trend_direction == "up" else "↓下降"
                lines.append(f"     趋势: 已连续 {e.trend_streak} 期{arrow}，再 {max(e.required_periods - e.trend_streak, 0)} 期即触发")
        lines.append("")

    if unknowns and show_all:
        lines.append("❓ 无数据（不得用空值判失效）")
        for e in unknowns:
            lines.append(f"  {e.ticker} {e.company_name} — {e.indicator_name}（{e.leg}）")
        lines.append("")

    s = summarize(evals)
    lines.append(
        f"汇总: {s['tickers']} 个持仓 / {s['total']} 条腿 — "
        f"触发 {s['triggered']} · 红 {s['red']} · 黄 {s['neutral']} · 绿 {s['positive']} · 未知 {s['unknown']}"
    )
    return "\n".join(lines)
