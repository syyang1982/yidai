"""Tests for the DCF valuation module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.dcf import simple_dcf, dcf_valuation, estimate_growth_rate


class TestSimpleDCF:
    """Test simple_dcf with known values."""

    def test_basic_dcf(self):
        """Known FCF with simple growth => verify intrinsic value."""
        result = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.10, 0.10, 0.10],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=100,
        )
        # FCF projections: 1100, 1210, 1331
        assert len(result["projected_fcfs"]) == 3
        assert abs(result["projected_fcfs"][0] - 1100.0) < 0.01
        assert abs(result["projected_fcfs"][1] - 1210.0) < 0.01
        assert abs(result["projected_fcfs"][2] - 1331.0) < 0.01
        # Terminal value = 1331 * 1.03 / (0.10 - 0.03) = 1370.93 / 0.07 ≈ 19584.71
        assert result["terminal_value"] > 19000
        assert result["terminal_value"] < 20000
        # Intrinsic value should be positive
        assert result["intrinsic_value"] > 0

    def test_single_year_growth(self):
        """Single year projection."""
        result = simple_dcf(
            current_fcf=500.0,
            growth_rates=[0.20],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=50,
        )
        assert len(result["projected_fcfs"]) == 1
        assert abs(result["projected_fcfs"][0] - 600.0) < 0.01
        assert result["intrinsic_value"] > 0

    def test_zero_growth_rates(self):
        """Zero growth rates list => uses current FCF for terminal value."""
        result = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=100,
        )
        assert result["projected_fcfs"] == []
        assert result["terminal_value"] > 0
        assert result["intrinsic_value"] > 0

    def test_negative_growth(self):
        """Negative growth rates should reduce intrinsic value."""
        result_neg = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[-0.10, -0.10],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=100,
        )
        result_pos = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.10, 0.10],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=100,
        )
        assert result_neg["intrinsic_value"] < result_pos["intrinsic_value"]

    def test_higher_discount_rate_reduces_value(self):
        """Higher discount rate => lower intrinsic value."""
        result_low = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.10] * 5,
            terminal_growth=0.03,
            discount_rate=0.08,
            shares_outstanding=100,
        )
        result_high = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.10] * 5,
            terminal_growth=0.03,
            discount_rate=0.15,
            shares_outstanding=100,
        )
        assert result_low["intrinsic_value"] > result_high["intrinsic_value"]


class TestSimpleDCFEdgeCases:
    """Edge cases for simple_dcf."""

    def test_zero_shares(self):
        """Zero shares => intrinsic_value = 0."""
        result = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.10],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=0,
        )
        assert result["intrinsic_value"] == 0.0

    def test_negative_shares(self):
        """Negative shares => intrinsic_value = 0."""
        result = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.10],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=-100,
        )
        assert result["intrinsic_value"] == 0.0

    def test_discount_rate_equals_terminal_growth(self):
        """discount_rate == terminal_growth => formula diverges, should handle gracefully."""
        result = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.10],
            terminal_growth=0.10,
            discount_rate=0.10,
            shares_outstanding=100,
        )
        # Should still produce a finite positive value (fallback reduces terminal_growth)
        assert result["intrinsic_value"] > 0
        assert result["intrinsic_value"] < float("inf")

    def test_terminal_growth_exceeds_discount_rate(self):
        """terminal_growth > discount_rate => should cap terminal_growth."""
        result = simple_dcf(
            current_fcf=1000.0,
            growth_rates=[0.05],
            terminal_growth=0.15,
            discount_rate=0.10,
            shares_outstanding=100,
        )
        assert result["intrinsic_value"] > 0
        assert result["intrinsic_value"] < float("inf")

    def test_negative_fcf(self):
        """Negative FCF still computes (though unrealistic)."""
        result = simple_dcf(
            current_fcf=-500.0,
            growth_rates=[0.10],
            terminal_growth=0.03,
            discount_rate=0.10,
            shares_outstanding=100,
        )
        # Terminal value will be negative
        assert result["intrinsic_value"] < 0


class TestDCFValuation:
    """Test dcf_valuation scoring thresholds."""

    def test_score_5_high_margin(self):
        """margin_of_safety > 30% => score 5."""
        # FCF=1000, shares=10, price=10 => very cheap
        financial = {
            "fcf": 1000.0,
            "shares_outstanding": 10.0,
            "revenue_growth_rates": [0.15, 0.12, 0.10, 0.08, 0.06],
        }
        price = {"current_price": 10.0}
        result = dcf_valuation(financial, price)
        assert result["score"] == 5
        assert result["margin_of_safety"] > 0.30

    def test_score_4_moderate_margin(self):
        """margin_of_safety in (15%, 30%] => score 4."""
        # Tune parameters to hit this range
        financial = {
            "fcf": 500.0,
            "shares_outstanding": 100.0,
            "revenue_growth_rates": [0.08],
        }
        # Calculate what intrinsic value would be, then set price for 20% margin
        temp = simple_dcf(500.0, [0.08 * 0.9 ** i for i in range(1)], 0.03, 0.10, 100.0)
        target_price = temp["intrinsic_value"] * 0.80  # 20% margin
        price = {"current_price": target_price}
        result = dcf_valuation(financial, price)
        assert result["score"] == 4
        assert 0.15 < result["margin_of_safety"] <= 0.30

    def test_score_3_small_margin(self):
        """margin_of_safety in (0%, 15%] => score 3."""
        financial = {
            "fcf": 500.0,
            "shares_outstanding": 100.0,
            "revenue_growth_rates": [0.08],
        }
        temp = simple_dcf(500.0, [0.08 * 0.9 ** i for i in range(1)], 0.03, 0.10, 100.0)
        target_price = temp["intrinsic_value"] * 0.95  # 5% margin
        price = {"current_price": target_price}
        result = dcf_valuation(financial, price)
        assert result["score"] == 3
        assert 0.0 < result["margin_of_safety"] <= 0.15

    def test_score_2_slight_overvalued(self):
        """margin_of_safety in (-15%, 0%] => score 2."""
        financial = {
            "fcf": 500.0,
            "shares_outstanding": 100.0,
            "revenue_growth_rates": [0.08],
        }
        temp = simple_dcf(500.0, [0.08 * 0.9 ** i for i in range(1)], 0.03, 0.10, 100.0)
        target_price = temp["intrinsic_value"] * 1.10  # 10% overvalued
        price = {"current_price": target_price}
        result = dcf_valuation(financial, price)
        assert result["score"] == 2
        assert -0.15 < result["margin_of_safety"] <= 0.0

    def test_score_1_overvalued(self):
        """margin_of_safety <= -15% => score 1."""
        financial = {
            "fcf": 500.0,
            "shares_outstanding": 100.0,
            "revenue_growth_rates": [0.08],
        }
        temp = simple_dcf(500.0, [0.08 * 0.9 ** i for i in range(1)], 0.03, 0.10, 100.0)
        target_price = temp["intrinsic_value"] * 1.50  # 50% overvalued
        price = {"current_price": target_price}
        result = dcf_valuation(financial, price)
        assert result["score"] == 1
        assert result["margin_of_safety"] <= -0.15

    def test_negative_fcf_score_1(self):
        """Negative FCF => score 1."""
        financial = {"fcf": -1000.0, "shares_outstanding": 100.0}
        price = {"current_price": 50.0}
        result = dcf_valuation(financial, price)
        assert result["score"] == 1

    def test_missing_fcf_score_3(self):
        """No FCF data => score 3 (neutral)."""
        financial = {"shares_outstanding": 100.0}
        price = {"current_price": 50.0}
        result = dcf_valuation(financial, price)
        assert result["score"] == 3

    def test_missing_price_score_3(self):
        """No price data => score 3 (neutral)."""
        financial = {"fcf": 1000.0, "shares_outstanding": 100.0}
        price = {}
        result = dcf_valuation(financial, price)
        assert result["score"] == 3

    def test_details_populated(self):
        """Details list should have meaningful content."""
        financial = {
            "fcf": 1000.0,
            "shares_outstanding": 100.0,
            "revenue_growth_rates": [0.10, 0.08],
        }
        price = {"current_price": 50.0}
        result = dcf_valuation(financial, price)
        assert len(result["details"]) >= 3
        assert any("FCF" in d for d in result["details"])
        assert any("margin_of_safety" in d for d in result["details"])

    def test_alternative_key_free_cash_flow(self):
        """Accepts 'free_cash_flow' as alternative to 'fcf'."""
        financial = {
            "free_cash_flow": 1000.0,
            "shares_outstanding": 100.0,
        }
        price = {"current_price": 1.0}
        result = dcf_valuation(financial, price)
        assert result["intrinsic_value"] > 0

    def test_uses_annual_data_for_growth(self):
        """Falls back to estimate_growth_rate when revenue_growth_rates absent."""
        financial = {
            "fcf": 500.0,
            "shares_outstanding": 100.0,
            "annual_data": [
                {"revenue": 1000},
                {"revenue": 1100},
                {"revenue": 1210},
                {"revenue": 1331},
            ],
        }
        price = {"current_price": 50.0}
        result = dcf_valuation(financial, price)
        assert result["score"] >= 1
        growth_detail = [d for d in result["details"] if "estimated growth" in d]
        assert len(growth_detail) > 0


class TestEstimateGrowthRate:
    """Test estimate_growth_rate with various data."""

    def test_normal_growth(self):
        """Consistent 10% growth."""
        data = [
            {"revenue": 1000},
            {"revenue": 1100},
            {"revenue": 1210},
            {"revenue": 1331},
        ]
        rate = estimate_growth_rate(data)
        assert abs(rate - 0.10) < 0.01

    def test_accelerating_growth(self):
        """Growth accelerating from 10% to 20%."""
        data = [
            {"revenue": 1000},
            {"revenue": 1100},  # +10%
            {"revenue": 1320},  # +20%
        ]
        rate = estimate_growth_rate(data)
        # Average of 10% and 20% = 15%
        assert abs(rate - 0.15) < 0.01

    def test_negative_growth(self):
        """Declining revenue."""
        data = [
            {"revenue": 1000},
            {"revenue": 900},
            {"revenue": 810},
        ]
        rate = estimate_growth_rate(data)
        assert rate < 0
        assert rate >= -0.20  # capped at -20%

    def test_extreme_growth_capped(self):
        """Very high growth should be capped at 50%."""
        data = [
            {"revenue": 100},
            {"revenue": 500},  # +400%
            {"revenue": 2500},  # +400%
        ]
        rate = estimate_growth_rate(data)
        assert rate <= 0.50

    def test_extreme_decline_capped(self):
        """Very large decline should be capped at -20%."""
        data = [
            {"revenue": 10000},
            {"revenue": 100},  # -99%
        ]
        rate = estimate_growth_rate(data)
        assert rate >= -0.20

    def test_single_year_default(self):
        """Single year => not enough data, returns default 5%."""
        data = [{"revenue": 1000}]
        rate = estimate_growth_rate(data)
        assert rate == 0.05

    def test_empty_data(self):
        """Empty list => default 5%."""
        rate = estimate_growth_rate([])
        assert rate == 0.05

    def test_missing_revenue_key(self):
        """Dicts without 'revenue' key => default 5%."""
        data = [{"profit": 100}, {"profit": 200}]
        rate = estimate_growth_rate(data)
        assert rate == 0.05

    def test_zero_revenue_skipped(self):
        """Zero revenue entries are skipped."""
        data = [
            {"revenue": 0},
            {"revenue": 1000},
            {"revenue": 1100},
        ]
        rate = estimate_growth_rate(data)
        # Only one valid growth period: (1100-1000)/1000 = 10%
        assert abs(rate - 0.10) < 0.01

    def test_uses_total_revenue_key(self):
        """Accepts 'total_revenue' as alternative key."""
        data = [
            {"total_revenue": 1000},
            {"total_revenue": 1200},
        ]
        rate = estimate_growth_rate(data)
        assert abs(rate - 0.20) < 0.01
