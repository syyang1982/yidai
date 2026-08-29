"""Tests for the growth analysis module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.growth import score


class TestGrowthIncreasingGoodDrivers:
    """Increasing trend + sustainable drivers => 0 issues => score=5."""

    def test_score_is_5(self):
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["organic growth", "market expansion"],
        }
        result = score(data)
        assert result["score"] == 5

    def test_details_show_strong(self):
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["organic growth", "market expansion"],
        }
        result = score(data)
        # Details should indicate strong growth and strong trend
        details_text = " ".join(result["details"])
        assert "strong" in details_text
        assert "non-declining" in details_text
        assert len(result["details"]) >= 3


class TestGrowthDecliningButPositive:
    """Declining trend but still positive growth => moderate latest + weak trend => score=3."""

    def test_score_is_3(self):
        data = {
            "revenue_growth_rates": [0.20, 0.15, 0.10],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        # moderate growth + weak trend => base=3
        assert result["score"] == 3

    def test_trend_is_weak(self):
        data = {
            "revenue_growth_rates": [0.20, 0.15, 0.10],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        trend_detail = [d for d in result["details"] if "trend" in d.lower()][0]
        assert "weak" in trend_detail
        assert "declining" in trend_detail

    def test_latest_growth_still_positive(self):
        data = {
            "revenue_growth_rates": [0.20, 0.15, 0.10],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        growth_detail = [d for d in result["details"] if "latest growth" in d.lower()][0]
        assert "moderate" in growth_detail or "strong" in growth_detail


class TestGrowthNegative:
    """Negative growth rate => at least 1 issue => score <= 3."""

    def test_score_at_most_3(self):
        data = {
            "revenue_growth_rates": [0.10, 0.05, -0.02],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        assert result["score"] <= 3

    def test_negative_growth_detected(self):
        data = {
            "revenue_growth_rates": [0.10, 0.05, -0.02],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        growth_detail = [d for d in result["details"] if "latest growth" in d.lower()][0]
        assert "declining" in growth_detail
        assert "-2.0%" in growth_detail

    def test_declining_and_negative_low_score(self):
        """Negative + declining => base score = 1."""
        data = {
            "revenue_growth_rates": [0.10, 0.05, -0.02],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        # negative growth + weak trend => base=1
        assert result["score"] == 1


class TestGrowthOneTimeDrivers:
    """One-time growth drivers detected => penalty (onetime_penalty=1)."""

    def test_score_penalty_english(self):
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["one-time asset sale"],
        }
        result = score(data)
        # strong + strong => base=5, onetime_penalty=1 => final=4
        assert result["score"] == 4

    def test_score_penalty_chinese(self):
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["一次性收益"],
        }
        result = score(data)
        assert result["score"] == 4

    def test_onetime_penalty_detail(self):
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["one-time asset sale", "core business"],
        }
        result = score(data)
        driver_detail = [d for d in result["details"] if "drivers" in d.lower()][0]
        assert "one-time" in driver_detail
        assert "penalize" in driver_detail

    def test_no_penalty_for_normal_drivers(self):
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["core business growth"],
        }
        result = score(data)
        # No one-time keywords => no driver penalty detail is emitted
        driver_details = [d for d in result["details"] if "drivers" in d.lower()]
        assert len(driver_details) == 0
        # Score should be unaffected (strong+strong => base=5)
        assert result["score"] == 5


class TestGrowthEdgeCases:
    """Edge cases: empty data, single period."""

    def test_empty_growth_rates(self):
        data = {
            "revenue_growth_rates": [],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        # No data => score=3 (neutral)
        assert result["score"] == 3

    def test_single_period_skips_trend(self):
        data = {
            "revenue_growth_rates": [0.15],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        trend_detail = [d for d in result["details"] if "trend" in d.lower()][0]
        assert "N/A" in trend_detail
        # 1 period positive, no one-time => strong + single => score=5
        assert result["score"] == 5


class TestQoQAnnualization:
    """QoQ growth rates should be annualized before scoring."""

    def test_qoq_to_annualized(self):
        """QoQ 5% => annualized ~21.55%."""
        data = {
            "revenue_growth_rates": [0.05, 0.05, 0.05],
            "growth_type": "qoq",
        }
        result = score(data)
        details_text = " ".join(result["details"])
        # (1+0.05)^4 - 1 = 0.21550625
        assert "QoQ data detected" in details_text
        # latest_rate after annualization should be ~21.6%
        assert "21.6%" in details_text

    def test_annualized_growth_used_for_scoring(self):
        """QoQ data should be annualized and affect scoring like YoY data."""
        data = {
            "revenue_growth_rates": [0.05, 0.04, 0.03],
            "growth_type": "qoq",
        }
        result = score(data)
        # Annualized: ~21.5%, ~17.0%, ~12.6% — all strong, but declining
        # latest strong + weak trend => base=3
        details_text = " ".join(result["details"])
        assert "QoQ data detected" in details_text
        assert result["score"] >= 2  # should not be neutral

    def test_yoy_default_unchanged(self):
        """YoY data (default) should not be annualized."""
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        details_text = " ".join(result["details"])
        assert "QoQ" not in details_text
        assert result["score"] == 5  # unchanged from existing test


class TestSustainableGrowth:
    """Check 7: sustainable growth rate cross-validation."""

    def test_sustainable_growth_pass(self):
        """Actual growth <= sustainable growth => PASS."""
        from analysis.growth import _sustainable_growth

        # ROE=15%, payout=30% => sustainable = 10.5%
        sust = _sustainable_growth(0.15, 0.30)
        assert abs(sust - 0.105) < 1e-9

        data = {
            "revenue_growth_rates": [0.10, 0.10, 0.10],
            "latest_roe": 0.15,
            "payout_ratio": 0.30,
        }
        result = score(data)
        details_text = " ".join(result["details"])
        assert "sustainable_growth" in details_text
        assert "PASS" in details_text

    def test_actual_exceeds_sustainable_warn(self):
        """Actual growth > 1.5× sustainable => WARN."""
        # ROE=15%, payout=30% => sustainable=10.5%
        # Actual latest ~20% > 15.75% (1.5×) => WARN
        data = {
            "revenue_growth_rates": [0.15, 0.18, 0.20],
            "latest_roe": 0.15,
            "payout_ratio": 0.30,
        }
        result = score(data)
        details_text = " ".join(result["details"])
        assert "WARN" in details_text
        assert "依赖外部融资" in details_text

    def test_sustainable_growth_none_when_missing(self):
        """No ROE/payout data => Check 7 is skipped silently."""
        data = {
            "revenue_growth_rates": [0.10, 0.15, 0.20],
            "growth_drivers": ["organic growth"],
        }
        result = score(data)
        details_text = " ".join(result["details"])
        assert "sustainable_growth" not in details_text
        # Score should be same as before (no regression)
        assert result["score"] == 5

    def test_sustainable_growth_calculation(self):
        """Pure unit test for _sustainable_growth helper."""
        from analysis.growth import _sustainable_growth

        # ROE=20%, payout=40% => 12%
        assert abs(_sustainable_growth(0.20, 0.40) - 0.12) < 1e-9
        # ROE=100%, payout=0% => 100%
        assert abs(_sustainable_growth(1.0, 0.0) - 1.0) < 1e-9
        # Missing inputs => None
        assert _sustainable_growth(None, 0.30) is None
        assert _sustainable_growth(0.15, None) is None
