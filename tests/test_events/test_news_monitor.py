"""Tests for NewsMonitor and ImpactAnalyzer."""
import pytest
from src.events.models import MarketEvent
from src.events.news_monitor import NewsMonitor, HIGH_IMPACT_KEYWORDS
from src.events.impact_analyzer import ImpactAnalyzer


# ── NewsMonitor unit tests ──────────────────────────────────────────────────

class TestIsHighImpact:
    def setup_method(self):
        self.nm = NewsMonitor()

    @pytest.mark.parametrize('keyword', HIGH_IMPACT_KEYWORDS)
    def test_each_keyword_detected(self, keyword):
        assert self.nm._is_high_impact(f'标题含{keyword}', '描述') is True

    def test_no_keyword_returns_false(self):
        assert self.nm._is_high_impact('普通新闻标题', '普通内容') is False

    def test_keyword_in_description_only(self):
        assert self.nm._is_high_impact('标题', '该公司财报超预期') is True


class TestExtractTickers:
    def setup_method(self):
        self.nm = NewsMonitor()
        self.names = {
            'LX': 'LexinFintech',
            '1810.HK': '小米',
            '9999.HK': '网易',
        }

    def test_matches_company_name(self):
        assert '1810.HK' in self.nm._extract_tickers('小米发布新手机', self.names)

    def test_matches_ticker_symbol(self):
        assert 'LX' in self.nm._extract_tickers('LX reported earnings', self.names)

    def test_no_match(self):
        assert self.nm._extract_tickers('无关新闻', self.names) == []

    def test_multiple_matches(self):
        text = '小米和网易同时发布财报'
        result = self.nm._extract_tickers(text, self.names)
        assert '1810.HK' in result
        assert '9999.HK' in result


class TestIsDuplicate:
    def test_identical_titles(self):
        assert NewsMonitor._is_duplicate('标题A', ['标题A']) is True

    def test_similar_titles(self):
        assert NewsMonitor._is_duplicate('小米发布财报超预期', ['小米发布财报超出预期']) is True

    def test_different_titles(self):
        assert NewsMonitor._is_duplicate('完全不同的标题', ['另一条新闻']) is False


# ── ImpactAnalyzer unit tests ──────────────────────────────────────────────

class TestAnalyzeEvent:
    def setup_method(self):
        self.analyzer = ImpactAnalyzer(portfolio_path='/nonexistent/path.json')

    def test_positive_direction(self):
        event = MarketEvent(
            event_id='t1', event_type='breaking', title='小米财报超预期增长',
            description='', event_date='2026-07-11', event_time='',
            affected_tickers=['1810.HK'], impact_level='high',
        )
        result = self.analyzer.analyze_event(event)
        assert result['tickers'][0]['direction'] == 'positive'
        assert '超预期' in result['summary'] or '📈' in result['summary']

    def test_negative_direction(self):
        event = MarketEvent(
            event_id='t2', event_type='breaking', title='某公司被制裁处罚',
            description='', event_date='2026-07-11', event_time='',
            affected_tickers=['LX'], impact_level='high',
        )
        result = self.analyzer.analyze_event(event)
        assert result['tickers'][0]['direction'] == 'negative'

    def test_neutral_direction(self):
        event = MarketEvent(
            event_id='t3', event_type='breaking', title='普通新闻',
            description='', event_date='2026-07-11', event_time='',
            affected_tickers=['9999.HK'], impact_level='low',
        )
        result = self.analyzer.analyze_event(event)
        assert result['tickers'][0]['direction'] == 'neutral'


class TestGenerateReport:
    def setup_method(self):
        self.analyzer = ImpactAnalyzer(portfolio_path='/nonexistent/path.json')

    def test_empty_events(self):
        report = self.analyzer.generate_daily_events_report([])
        assert '暂无重大事件' in report

    def test_report_format(self):
        events = [
            MarketEvent(
                event_id='r1', event_type='breaking', title='测试事件',
                description='desc', event_date='2026-07-11', event_time='10:00',
                affected_tickers=['1810.HK'], impact_level='high',
            ),
        ]
        report = self.analyzer.generate_daily_events_report(events)
        assert '今日市场事件报告' in report
        assert '测试事件' in report
        assert '🔴' in report

    def test_calendar_format(self):
        events = [
            MarketEvent(
                event_id='c1', event_type='earnings', title='财报日',
                description='desc', event_date='2026-07-20', event_time='',
                affected_tickers=['LX'], impact_level='medium',
            ),
        ]
        cal = self.analyzer.generate_upcoming_calendar(events, days=30)
        assert '事件日历' in cal
        assert '2026-07' in cal
        assert '财报日' in cal


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
