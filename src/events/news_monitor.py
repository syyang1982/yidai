"""News monitor — scans Google News RSS for breaking events affecting portfolio holdings."""
import re
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Dict, List

from src.events.models import MarketEvent

HIGH_IMPACT_KEYWORDS = [
    '财报', '盈利', '收购', '并购', 'IPO', '制裁', '禁令', '监管',
    '暴涨', '暴跌', '跌停', '涨停', '发射', '回收', '签约', '中标',
    'CEO', '换帅', '裁员', '重组', '增发', '回购', '突破', '创新高', '创新低',
]


class NewsMonitor:
    """Scans Google News RSS for breaking news affecting portfolio tickers."""

    GOOGLE_NEWS_RSS = (
        'https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans'
    )

    # ---- public API -----------------------------------------------------------

    def scan_breaking_news(
        self,
        portfolio_tickers: List[str],
        ticker_names: Dict[str, str] | None = None,
    ) -> List[MarketEvent]:
        """Return MarketEvent objects for high-impact articles in the last 24 h."""
        ticker_names = ticker_names or {}
        events: List[MarketEvent] = []
        seen_titles: List[str] = []

        for ticker in portfolio_tickers:
            name = ticker_names.get(ticker, ticker)
            query = f"{name} {ticker}"
            articles = self._search_rss(query, hours=24)

            for art in articles:
                title = art.get('title', '')
                if not title or self._is_duplicate(title, seen_titles):
                    continue
                seen_titles.append(title)

                desc = art.get('description', '')
                if not self._is_high_impact(title, desc):
                    continue

                matched_tickers = self._extract_tickers(
                    f"{title} {desc}", ticker_names
                ) or [ticker]

                now = datetime.now()
                event = MarketEvent(
                    event_id=uuid.uuid4().hex[:12],
                    event_type='breaking',
                    title=title,
                    description=desc,
                    event_date=now.strftime('%Y-%m-%d'),
                    event_time=now.strftime('%H:%M'),
                    affected_tickers=matched_tickers,
                    source='Google News',
                    source_url=art.get('link', ''),
                    impact_level='high',
                    impact_direction='neutral',
                )
                events.append(event)

        return events

    # ---- internals ------------------------------------------------------------

    def _search_rss(self, query: str, hours: int = 24) -> List[dict]:
        """Fetch & parse Google News RSS, returning articles within *hours* window."""
        url = self.GOOGLE_NEWS_RSS.format(query=query.replace(' ', '+'))
        try:
            result = subprocess.run(
                ['curl', '-sL', '--max-time', '15', url],
                capture_output=True, text=True, timeout=20,
            )
            xml = result.stdout
        except Exception:
            return []

        if not xml or '<item>' not in xml:
            return []

        # Split into items then extract fields per item
        items = re.split(r'<item>', xml)[1:]  # skip header
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        articles: List[dict] = []

        for item in items:
            title = self._first(r'<title>(.*?)</title>', item)
            link = self._first(r'<link>(.*?)</link>', item)
            pub_date_str = self._first(r'<pubDate>(.*?)</pubDate>', item)
            desc = self._first(
                r'<description><!\[CDATA\[(.*?)\]\]></description>', item, flags=re.DOTALL
            )

            # filter by time
            if pub_date_str:
                try:
                    pub_dt = self._parse_rfc822(pub_date_str)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass  # keep article if date unparseable

            articles.append({
                'title': title,
                'link': link,
                'pubDate': pub_date_str,
                'description': self._strip_html(desc),
            })

        return articles

    def _is_high_impact(self, title: str, description: str) -> bool:
        """True if title or description contains any high-impact keyword."""
        text = f"{title} {description}"
        return any(kw in text for kw in HIGH_IMPACT_KEYWORDS)

    def _extract_tickers(self, text: str, ticker_names: Dict[str, str]) -> List[str]:
        """Return tickers whose name (or ticker symbol) appears in text."""
        matched: List[str] = []
        for ticker, name in ticker_names.items():
            if name and name in text:
                matched.append(ticker)
            elif ticker in text and ticker not in matched:
                matched.append(ticker)
        return matched

    # ---- helpers ---------------------------------------------------------------

    @staticmethod
    def _first(pattern: str, text: str, flags: int = 0) -> str:
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else ''

    @staticmethod
    def _strip_html(text: str) -> str:
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _parse_rfc822(date_str: str) -> datetime:
        """Parse RFC-822 date (used in RSS) to aware UTC datetime."""
        # e.g. 'Mon, 07 Jul 2025 08:30:00 GMT'
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)

    @staticmethod
    def _is_duplicate(title: str, seen: List[str], threshold: float = 0.75) -> bool:
        for prev in seen:
            if SequenceMatcher(None, title, prev).ratio() >= threshold:
                return True
        return False
