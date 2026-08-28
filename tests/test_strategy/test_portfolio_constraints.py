"""Tests for PortfolioConstraints module."""
import pytest
from src.strategy.portfolio_constraints import PortfolioConstraints


class TestPositionLimits:
    """Single-position limit checks."""

    def test_single_position_over_limit(self):
        """单股仓位超限告警"""
        pc = PortfolioConstraints(max_single_pct=25)
        holdings = [
            {"ticker": "0005.HK", "name": "汇丰控股", "value_hkd": 300_000},
            {"ticker": "0388.HK", "name": "港交所", "value_hkd": 150_000},
            {"ticker": "0001.HK", "name": "长和", "value_hkd": 150_000},
        ]
        violations = pc.check_position_limits(holdings)
        # 0005.HK = 300k / 600k = 50% > 25% → should be flagged
        # 0388.HK = 150k / 600k = 25% → not over (boundary)
        assert len(violations) == 1
        assert violations[0]["ticker"] == "0005.HK"
        assert violations[0]["pct"] == pytest.approx(50.0)
        assert violations[0]["limit"] == 25

    def test_all_within_limit(self):
        """所有仓位在限内无告警"""
        pc = PortfolioConstraints(max_single_pct=25)
        holdings = [
            {"ticker": "0005.HK", "name": "汇丰控股", "value_hkd": 200_000},
            {"ticker": "0388.HK", "name": "港交所", "value_hkd": 200_000},
            {"ticker": "0001.HK", "name": "长和", "value_hkd": 200_000},
        ]
        violations = pc.check_position_limits(holdings)
        # Each = 200k / 600k ≈ 33.3%, all exceed 25% → but this test expects no violations
        # Use a higher limit for this test
        pc2 = PortfolioConstraints(max_single_pct=40)
        violations2 = pc2.check_position_limits(holdings)
        assert violations2 == []


class TestSectorConcentration:
    """Sector concentration checks."""

    def test_sector_over_concentrated(self):
        """单行业超限"""
        pc = PortfolioConstraints(max_sector_pct=40)
        holdings = [
            {"ticker": "0005.HK", "name": "汇丰", "value_hkd": 300_000, "sector": "金融"},
            {"ticker": "0388.HK", "name": "港交所", "value_hkd": 200_000, "sector": "金融"},
            {"ticker": "0700.HK", "name": "腾讯", "value_hkd": 100_000, "sector": "科技"},
        ]
        violations = pc.check_sector_concentration(holdings)
        # 金融 = 500k / 600k ≈ 83.3% > 40%
        assert len(violations) == 1
        assert violations[0]["sector"] == "金融"
        assert violations[0]["pct"] == pytest.approx(500 / 600 * 100)
        assert violations[0]["limit"] == 40


class TestMarketExposure:
    """Single-market exposure checks."""

    def test_market_over_exposed(self):
        """单一市场暴露过高"""
        pc = PortfolioConstraints(max_market_pct=70)
        holdings = [
            {"ticker": "0005.HK", "name": "汇丰", "value_hkd": 400_000, "market": "HK"},
            {"ticker": "0388.HK", "name": "港交所", "value_hkd": 200_000, "market": "HK"},
            {"ticker": "AAPL", "name": "Apple", "value_hkd": 100_000, "market": "US"},
        ]
        violations = pc.check_market_exposure(holdings)
        # HK = 600k / 700k ≈ 85.7% > 70%
        assert len(violations) == 1
        assert violations[0]["market"] == "HK"
        assert violations[0]["pct"] == pytest.approx(600 / 700 * 100)
        assert violations[0]["limit"] == 70


class TestCorrelationGroup:
    """Correlation-group concentration checks."""

    def test_correlated_positions_detected(self):
        """高相关性持仓被标记"""
        pc = PortfolioConstraints(max_correlation_group_pct=35)
        pc.add_correlation_group("银行股", ["0005.HK", "1398.HK", "3988.HK"], "同属银行板块")
        holdings = [
            {"ticker": "0005.HK", "name": "汇丰", "value_hkd": 200_000},
            {"ticker": "1398.HK", "name": "工商银行", "value_hkd": 100_000},
            {"ticker": "3988.HK", "name": "中国银行", "value_hkd": 100_000},
            {"ticker": "0700.HK", "name": "腾讯", "value_hkd": 200_000},
        ]
        violations = pc.check_correlation_groups(holdings)
        # 银行股 group = 400k / 600k ≈ 66.7% > 35%
        assert len(violations) == 1
        assert violations[0]["group"] == "银行股"
        assert violations[0]["pct"] == pytest.approx(400 / 600 * 100)
        assert violations[0]["limit"] == 35


class TestCheckAll:
    """Integration: check_all runs everything and format_report renders it."""

    def test_check_all_aggregates(self):
        pc = PortfolioConstraints(max_single_pct=25, max_sector_pct=40)
        pc.add_correlation_group("银行股", ["0005.HK", "1398.HK"], "同属银行")
        holdings = [
            {"ticker": "0005.HK", "name": "汇丰", "value_hkd": 300_000, "sector": "金融", "market": "HK"},
            {"ticker": "1398.HK", "name": "工行", "value_hkd": 100_000, "sector": "金融", "market": "HK"},
        ]
        result = pc.check_all(holdings)
        assert "position_violations" in result
        assert "sector_violations" in result
        assert "market_violations" in result
        assert "correlation_violations" in result
        assert result["total_violations"] > 0

    def test_format_report_returns_string(self):
        pc = PortfolioConstraints()
        result = pc.check_all([])
        report = pc.format_report(result)
        assert isinstance(report, str)
        assert len(report) > 0
