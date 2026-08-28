"""Impact analyzer — rule-based event analysis and report generation."""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List

from src.events.models import MarketEvent

POSITIVE_KEYWORDS = ['超预期', '增长', '突破', '利好', '上涨', '反弹', '创高', '收购']
NEGATIVE_KEYWORDS = ['低于预期', '下降', '利空', '处罚', '下跌', '暴跌', '制裁', '禁令', '裁员']

SEVERITY_EMOJI = {'high': '🔴', 'medium': '🟡', 'low': '🔵'}
DIRECTION_EMOJI = {'positive': '📈', 'negative': '📉', 'neutral': '➡️'}


class ImpactAnalyzer:
    """Rule-based event impact analyzer and report generator."""

    def __init__(self, portfolio_path: str = '~/.hermes/portfolio_data.json'):
        self.portfolio_path = os.path.expanduser(portfolio_path)
        self.portfolio = self._load_portfolio()

    # ---- public API -----------------------------------------------------------

    def analyze_event(self, event: MarketEvent) -> dict:
        """Return impact analysis for a single event."""
        text = f"{event.title} {event.description}"
        direction = self._detect_direction(text)

        ticker_impacts = []
        for ticker in event.affected_tickers:
            ticker_impacts.append({
                'ticker': ticker,
                'impact': event.impact_level,
                'direction': direction,
                'suggestion': self._suggest(event.impact_level, direction),
            })

        emoji = SEVERITY_EMOJI.get(event.impact_level, '🔵')
        dir_emoji = DIRECTION_EMOJI.get(direction, '➡️')
        summary = f"{emoji}{dir_emoji} {event.title} | 影响: {event.impact_level} | 方向: {direction}"

        return {'tickers': ticker_impacts, 'summary': summary}

    def generate_daily_events_report(self, events: List[MarketEvent]) -> str:
        """Chinese markdown daily events report."""
        if not events:
            return '# 📰 今日市场事件报告\n\n暂无重大事件。'

        lines = [
            '# 📰 今日市场事件报告',
            f'> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            '',
        ]

        # Group by impact level
        by_level: Dict[str, List[MarketEvent]] = defaultdict(list)
        for ev in events:
            by_level[ev.impact_level].append(ev)

        for level in ('high', 'medium', 'low'):
            group = by_level.get(level, [])
            if not group:
                continue
            emoji = SEVERITY_EMOJI[level]
            label = {'high': '高影响', 'medium': '中影响', 'low': '低影响'}[level]
            lines.append(f'## {emoji} {label}事件 ({len(group)})')
            lines.append('')

            for ev in group:
                analysis = self.analyze_event(ev)
                dir_emoji = DIRECTION_EMOJI.get(analysis['summary'][2:11] if len(analysis['summary']) > 10 else '', '➡️')
                tickers_str = ', '.join(ev.affected_tickers)
                lines.append(f'### {ev.title}')
                lines.append(f'- **标的**: {tickers_str}')
                lines.append(f'- **来源**: {ev.source}')
                lines.append(f'- **分析**: {analysis["summary"]}')
                if ev.source_url:
                    lines.append(f'- **链接**: {ev.source_url}')
                lines.append('')

        return '\n'.join(lines)

    def generate_upcoming_calendar(self, events: List[MarketEvent], days: int = 30) -> str:
        """Calendar view of upcoming events grouped by month/day."""
        cutoff = datetime.now() + timedelta(days=days)
        upcoming = []
        for ev in events:
            try:
                dt = datetime.strptime(ev.event_date, '%Y-%m-%d')
                if datetime.now() <= dt <= cutoff:
                    upcoming.append(ev)
            except ValueError:
                continue

        if not upcoming:
            return f'# 📅 未来{days}天事件日历\n\n暂无已知事件。'

        upcoming.sort(key=lambda e: e.event_date)
        lines = [
            f'# 📅 未来{days}天事件日历',
            f'> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            '',
        ]

        by_month: Dict[str, List[MarketEvent]] = defaultdict(list)
        for ev in upcoming:
            month_key = ev.event_date[:7]  # YYYY-MM
            by_month[month_key].append(ev)

        for month, month_events in by_month.items():
            lines.append(f'## 📆 {month}')
            lines.append('')
            lines.append('| 日期 | 事件 | 影响 | 涉及标的 |')
            lines.append('|------|------|------|----------|')

            for ev in month_events:
                emoji = SEVERITY_EMOJI.get(ev.impact_level, '🔵')
                tickers = ', '.join(ev.affected_tickers)
                lines.append(f'| {ev.event_date} | {ev.title} | {emoji} | {tickers} |')

            lines.append('')

        return '\n'.join(lines)

    # ---- internals ------------------------------------------------------------

    def _load_portfolio(self) -> dict:
        try:
            with open(self.portfolio_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {'holdings': [], 'prices': {}, 'strategy': {}}

    @staticmethod
    def _detect_direction(text: str) -> str:
        pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
        if pos > neg:
            return 'positive'
        if neg > pos:
            return 'negative'
        return 'neutral'

    @staticmethod
    def _suggest(impact: str, direction: str) -> str:
        if impact == 'high' and direction == 'negative':
            return '⚠️ 密切关注，考虑减仓或设置止损'
        if impact == 'high' and direction == 'positive':
            return '✅ 利好确认后可适当加仓'
        if impact == 'medium' and direction == 'negative':
            return '🔍 持续跟踪，暂不操作'
        if impact == 'medium' and direction == 'positive':
            return '🔍 保持关注，等待确认'
        return '📋 记录备案，常规跟踪'
