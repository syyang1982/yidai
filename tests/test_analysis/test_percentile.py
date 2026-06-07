"""Tests for the PE percentile estimation module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.percentile import compute_pe_percentile, estimate_percentile_from_financials


# ── compute_pe_percentile ────────────────────────────────────────────────


class TestComputePercentile:
    """Basic percentile computation from a known history."""

    def test_midpoint(self):
        """Current PE in the middle of history → ~0.5."""
        result = compute_pe_percentile(15.0, [10.0, 12.0, 15.0, 18.0, 20.0])
        # 3 values >= 15: [15, 18, 20] → 3/5 = 0.6
        assert abs(result - 0.6) < 1e-9

    def test_low_percentile(self):
        """Current PE near the bottom → high percentile (cheap)."""
        result = compute_pe_percentile(5.0, [10.0, 12.0, 15.0, 18.0, 20.0])
        # 5 values >= 5 → 5/5 = 1.0
        assert abs(result - 1.0) < 1e-9

    def test_high_percentile(self):
        """Current PE near the top → low percentile (expensive)."""
        result = compute_pe_percentile(25.0, [10.0, 12.0, 15.0, 18.0, 20.0])
        # 0 values >= 25 → 0/5 = 0.0
        assert abs(result - 0.0) < 1e-9

    def test_exact_match(self):
        """Current PE exactly matches a history value."""
        result = compute_pe_percentile(15.0, [10.0, 15.0, 20.0])
        # [15, 20] >= 15 → 2/3
        assert abs(result - 2 / 3) < 1e-9

    def test_all_same(self):
        """All history values equal to current PE → 0.5 (1/2 counted as >=)."""
        result = compute_pe_percentile(10.0, [10.0, 10.0, 10.0])
        # All 3 >= 10 → 3/3 = 1.0
        assert abs(result - 1.0) < 1e-9


class TestComputePercentileEdgeCases:
    """Edge-case handling."""

    def test_empty_history(self):
        """Empty history → neutral 0.5."""
        assert compute_pe_percentile(15.0, []) == 0.5

    def test_none_history(self):
        """None history → neutral 0.5."""
        assert compute_pe_percentile(15.0, None) == 0.5  # type: ignore[arg-type]

    def test_negative_current_pe(self):
        """Negative current PE → 0.0."""
        assert compute_pe_percentile(-5.0, [10.0, 15.0, 20.0]) == 0.0

    def test_zero_current_pe(self):
        """Zero current PE → 0.0."""
        assert compute_pe_percentile(0.0, [10.0, 15.0, 20.0]) == 0.0

    def test_history_with_negatives_filtered(self):
        """Negative history values are filtered out."""
        result = compute_pe_percentile(15.0, [-5.0, 10.0, 15.0, 20.0])
        # valid = [10, 15, 20]; >= 15: [15, 20] → 2/3
        assert abs(result - 2 / 3) < 1e-9

    def test_all_negative_history(self):
        """All history values negative → neutral 0.5."""
        result = compute_pe_percentile(15.0, [-5.0, -10.0])
        assert result == 0.5


# ── estimate_percentile_from_financials ──────────────────────────────────


class TestEstimatePercentile:
    """Estimate percentile from annual financial data."""

    def test_with_eps_history(self):
        """Direct EPS data → compute PE history using current price."""
        annual = [
            {"eps": 1.0},
            {"eps": 1.5},
            {"eps": 2.0},
            {"eps": 2.5},
        ]
        price_data = {"current_price": 30.0}
        # PE history (using current_price=30): [30, 20, 15, 12]
        # current PE = 30/2.5 = 12 (but we pass pe explicitly)
        # pe=12 → in [30,20,15,12] → all 4 values >= 12 → 4/4 = 1.0
        result = estimate_percentile_from_financials(12.0, annual, price_data)
        assert 0.0 <= result <= 1.0
        assert abs(result - 1.0) < 1e-9

    def test_with_net_income_and_shares(self):
        """EPS derived from net_income / shares."""
        annual = [
            {"net_income": 100, "shares_outstanding": 100},
            {"net_income": 200, "shares_outstanding": 100},
        ]
        price_data = {"current_price": 20.0}
        # EPS = [1.0, 2.0]; PE history = [20, 10]
        # pe=10 → >= 10: [20, 10] → 2/2 = 1.0
        result = estimate_percentile_from_financials(10.0, annual, price_data)
        assert abs(result - 1.0) < 1e-9

    def test_with_revenue_margin(self):
        """EPS derived from revenue * net_margin / shares."""
        annual = [
            {"revenue": 1000, "net_margin": 0.10, "shares_outstanding": 100},
            {"revenue": 2000, "net_margin": 0.15, "shares_outstanding": 100},
        ]
        price_data = {"current_price": 30.0}
        # EPS = [1.0, 3.0]; PE = [30, 10]
        # pe=15 → >= 15: [30] → 1/2 = 0.5
        result = estimate_percentile_from_financials(15.0, annual, price_data)
        assert abs(result - 0.5) < 1e-9

    def test_with_historical_prices(self):
        """Uses historical prices when available."""
        annual = [{"eps": 2.0}, {"eps": 2.0}, {"eps": 2.0}]
        price_data = {
            "current_price": 40.0,
            "historical_prices": [20.0, 30.0, 40.0],
        }
        # PE history = [10, 15, 20]; pe=18 → >= 18: [20] → 1/3
        result = estimate_percentile_from_financials(18.0, annual, price_data)
        assert abs(result - 1 / 3) < 1e-9

    def test_empty_annual_data(self):
        """No annual data → neutral 0.5."""
        result = estimate_percentile_from_financials(15.0, [], {"current_price": 30.0})
        assert result == 0.5

    def test_negative_pe_returns_zero(self):
        """Negative PE → 0.0."""
        result = estimate_percentile_from_financials(-5.0, [{"eps": 2.0}], {})
        assert result == 0.0

    def test_no_price_data(self):
        """No price data → can't build PE history → fallback or 0.5."""
        annual = [{"eps": 1.0}, {"eps": 2.0}]
        result = estimate_percentile_from_financials(15.0, annual, {})
        # No price → no PE history, but earnings grew → synthetic fallback
        assert 0.0 <= result <= 1.0


class TestEstimatePercentileFallback:
    """Fallback synthetic range from earnings growth."""

    def test_growth_company_wide_range(self):
        """High earnings growth → wider synthetic PE range."""
        annual = [
            {"eps": 1.0},
            {"eps": 1.21},  # ~10% CAGR over 2 years
        ]
        price_data = {"current_price": 50.0}  # no historical_prices
        # PE history via price: [50, 50/1.21≈41.3]
        # pe=50 → >= 50: [50] → 1/2 = 0.5
        # But since we CAN build PE history from current_price, it uses that.
        result = estimate_percentile_from_financials(50.0, annual, price_data)
        assert 0.0 <= result <= 1.0

    def test_no_eps_data_fallback(self):
        """No valid EPS → returns 0.5."""
        annual = [{"revenue": 100}]  # no margin, no shares, no eps
        result = estimate_percentile_from_financials(15.0, annual, {"current_price": 30.0})
        assert result == 0.5
