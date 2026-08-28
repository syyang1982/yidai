"""
事件日历文件管理器 — 生成人可读的markdown日历文件

所有用户可见文本为中文。
"""

import os
from datetime import date, datetime
from typing import List, Dict
from collections import defaultdict

from src.events.models import MarketEvent


class CalendarWriter:
    """生成/更新事件日历markdown文件。"""

    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                "knowledge", "events"
            )
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def write_calendar(self, events: List[MarketEvent], filepath: str = None) -> str:
        """写入事件日历文件，返回文件路径。"""
        if filepath is None:
            filepath = os.path.join(self.output_dir, "calendar.md")

        lines = []
        lines.append("# 投资事件日历")
        lines.append("")
        lines.append(f"> 最后更新: {date.today().isoformat()}")
        lines.append(f"> 事件总数: {len(events)}")
        lines.append("")

        # 按月份分组
        by_month = defaultdict(list)
        for e in events:
            if e.event_date:
                month_key = e.event_date[:7]  # YYYY-MM
                by_month[month_key].append(e)

        for month_key in sorted(by_month.keys()):
            month_events = sorted(by_month[month_key], key=lambda e: e.event_date)
            year, month = month_key.split("-")
            lines.append(f"## {year}年{int(month)}月")
            lines.append("")
            lines.append("| 日期 | 事件 | 关联标的 | 影响 | 类型 | 状态 |")
            lines.append("|------|------|---------|------|------|------|")

            for e in month_events:
                day = e.event_date[5:]  # MM-DD
                tickers_str = ", ".join(e.affected_tickers[:3]) if e.affected_tickers else "—"
                if len(e.affected_tickers) > 3:
                    tickers_str += f" +{len(e.affected_tickers)-3}"
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(e.impact_level, "⚪")
                type_label = {
                    "earnings": "财报", "macro": "宏观", "product": "产品",
                    "breaking": "突发", "ipo": "IPO", "dividend": "分红",
                    "regulatory": "监管",
                }.get(e.event_type, e.event_type)
                status = "✅已通知" if e.notified else "⏳待定"
                lines.append(
                    f"| {day} | {e.title} | {tickers_str} | {impact_icon} | {type_label} | {status} |"
                )

            lines.append("")

        # 突发事件记录
        breaking = [e for e in events if e.event_type == "breaking"]
        if breaking:
            lines.append("## 突发事件记录")
            lines.append("")
            lines.append("| 日期 | 事件 | 关联标的 | 影响 | 来源 |")
            lines.append("|------|------|---------|------|------|")
            for e in sorted(breaking, key=lambda e: e.event_date, reverse=True):
                tickers_str = ", ".join(e.affected_tickers[:3]) if e.affected_tickers else "—"
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(e.impact_level, "⚪")
                lines.append(
                    f"| {e.event_date[5:]} | {e.title} | {tickers_str} | {impact_icon} | {e.source} |"
                )
            lines.append("")

        content = "\n".join(lines)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def format_daily_briefing(self, events: List[MarketEvent]) -> str:
        """格式化每日事件简报。"""
        today = date.today().isoformat()
        today_events = [e for e in events if e.event_date == today]
        tomorrow = date.fromordinal(date.today().toordinal() + 1).isoformat()
        tomorrow_events = [e for e in events if e.event_date == tomorrow]

        lines = []
        lines.append(f"━━━ {today} 事件简报 ━━━")
        lines.append("")

        if not today_events and not tomorrow_events:
            lines.append("✅ 今日无重要事件")
            return "\n".join(lines)

        # 今日事件
        if today_events:
            lines.append("📅 今日事件:")
            for e in sorted(today_events, key=lambda e: {"high": 0, "medium": 1, "low": 2}.get(e.impact_level, 3)):
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(e.impact_level, "⚪")
                tickers_str = ", ".join(e.affected_tickers[:3]) if e.affected_tickers else "—"
                direction = {"positive": "⬆利好", "negative": "⬇利空", "neutral": "➡中性"}.get(e.impact_direction, "")
                lines.append(f"  {impact_icon} {e.title} → {tickers_str} {direction}")
                if e.impact_analysis:
                    lines.append(f"     {e.impact_analysis}")
            lines.append("")

        # 明日预告
        if tomorrow_events:
            lines.append("📆 明日预告:")
            for e in sorted(tomorrow_events, key=lambda e: {"high": 0, "medium": 1, "low": 2}.get(e.impact_level, 3)):
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(e.impact_level, "⚪")
                tickers_str = ", ".join(e.affected_tickers[:3]) if e.affected_tickers else "—"
                lines.append(f"  {impact_icon} {e.title} → {tickers_str}")
            lines.append("")

        # 高影响事件操作建议
        high_events = [e for e in today_events if e.impact_level == "high"]
        if high_events:
            lines.append("⚡ 高影响事件操作建议:")
            for e in high_events:
                lines.append(f"  • {e.title}")
                if e.impact_analysis:
                    lines.append(f"    {e.impact_analysis}")
            lines.append("")

        return "\n".join(lines)

    def format_weekly_preview(self, events: List[MarketEvent]) -> str:
        """格式化下周事件预览。"""
        today = date.today()
        week_start = date.fromordinal(today.toordinal() + (7 - today.weekday()))
        week_end = date.fromordinal(week_start.toordinal() + 6)

        week_events = [
            e for e in events
            if week_start.isoformat() <= e.event_date <= week_end.isoformat()
        ]

        lines = []
        lines.append(f"━━━ 下周事件预览 ({week_start.isoformat()} ~ {week_end.isoformat()}) ━━━")
        lines.append("")

        if not week_events:
            lines.append("下周无重要事件")
            return "\n".join(lines)

        # 按日期分组
        by_date = defaultdict(list)
        for e in week_events:
            by_date[e.event_date].append(e)

        for d in sorted(by_date.keys()):
            day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            dt = date.fromisoformat(d)
            day_label = f"{d[5:]} {day_name[dt.weekday()]}"
            lines.append(f"📌 {day_label}:")
            for e in by_date[d]:
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(e.impact_level, "⚪")
                tickers_str = ", ".join(e.affected_tickers[:3]) if e.affected_tickers else "—"
                lines.append(f"   {impact_icon} {e.title} → {tickers_str}")
            lines.append("")

        # 策略建议
        high_events = [e for e in week_events if e.impact_level == "high"]
        if high_events:
            lines.append("⚡ 本周重点关注:")
            for e in high_events:
                lines.append(f"  • {e.title} ({e.event_date[5:]})")
            lines.append("")

        return "\n".join(lines)
