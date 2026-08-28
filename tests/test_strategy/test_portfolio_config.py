"""Tests for portfolio configuration module."""
from __future__ import annotations

from src.strategy.portfolio_config import get_default_constraints, create_sample_holdings


class TestGetDefaultConstraints:
    """Tests for get_default_constraints()."""

    def test_returns_portfolio_constraints_instance(self):
        from src.strategy.portfolio_constraints import PortfolioConstraints
        pc = get_default_constraints()
        assert isinstance(pc, PortfolioConstraints)

    def test_default_limits(self):
        pc = get_default_constraints()
        assert pc.max_single_pct == 25.0
        assert pc.max_sector_pct == 40.0
        assert pc.max_market_pct == 70.0
        assert pc.max_correlation_group_pct == 35.0

    def test_correlation_groups_configured(self):
        pc = get_default_constraints()
        # Should have 4 correlation groups
        assert len(pc._correlation_groups) == 4

    def test_correlation_group_names(self):
        pc = get_default_constraints()
        names = {g["name"] for g in pc._correlation_groups}
        assert "金山系" in names
        assert "小米生态" in names
        assert "港股互联网" in names
        assert "港股消费" in names

    def test_jinshan_group_tickers(self):
        pc = get_default_constraints()
        group = next(g for g in pc._correlation_groups if g["name"] == "金山系")
        assert "3888.HK" in group["tickers"]
        assert "3896.HK" in group["tickers"]

    def test_xiaomi_eco_group_tickers(self):
        pc = get_default_constraints()
        group = next(g for g in pc._correlation_groups if g["name"] == "小米生态")
        assert "01810.HK" in group["tickers"]
        assert "3896.HK" in group["tickers"]

    def test_correlation_groups_have_reasons(self):
        pc = get_default_constraints()
        for g in pc._correlation_groups:
            assert "reason" in g
            assert len(g["reason"]) > 0


class TestCreateSampleHoldings:
    """Tests for create_sample_holdings()."""

    def test_returns_list_of_dicts(self):
        holdings = create_sample_holdings()
        assert isinstance(holdings, list)
        assert all(isinstance(h, dict) for h in holdings)

    def test_required_keys(self):
        holdings = create_sample_holdings()
        required = {"ticker", "name", "value_hkd", "sector", "market"}
        for h in holdings:
            assert required.issubset(h.keys()), f"Missing keys in {h}"

    def test_total_value_approximately_1m(self):
        holdings = create_sample_holdings()
        total = sum(h["value_hkd"] for h in holdings)
        assert 900_000 <= total <= 1_100_000, f"Total {total} not ~1M"

    def test_xiaomi_is_largest_holding(self):
        holdings = create_sample_holdings()
        xiaomi = next(h for h in holdings if h["ticker"] == "01810.HK")
        max_other = max(h["value_hkd"] for h in holdings if h["ticker"] != "01810.HK")
        assert xiaomi["value_hkd"] >= max_other

    def test_contains_all_sample_tickers(self):
        holdings = create_sample_holdings()
        tickers = {h["ticker"] for h in holdings}
        expected = {"01810.HK", "3896.HK", "3888.HK", "09988.HK", "9896.HK"}
        assert expected.issubset(tickers)

    def test_no_negative_values(self):
        holdings = create_sample_holdings()
        assert all(h["value_hkd"] > 0 for h in holdings)
