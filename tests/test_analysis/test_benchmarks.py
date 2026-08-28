"""Tests for the industry benchmarks module (W3.1)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.benchmarks import get_benchmark, relative_score, INDUSTRY_BENCHMARKS


class TestGetBenchmarkKnownSector:
    """get_benchmark returns correct data for known sectors."""

    def test_technology(self):
        bench = get_benchmark("technology")
        assert bench["median_gross_margin"] == 0.45
        assert bench["median_net_margin"] == 0.12
        assert bench["median_roe"] == 0.14
        assert bench["median_debt_ratio"] == 0.35
        assert bench["median_revenue_growth"] == 0.15
        assert bench["typical_pe_range"] == (25, 60)

    def test_auto_parts(self):
        bench = get_benchmark("auto_parts")
        assert bench["median_gross_margin"] == 0.22

    def test_case_insensitive(self):
        bench = get_benchmark("Technology")
        assert bench["median_gross_margin"] == 0.45

    def test_with_spaces(self):
        bench = get_benchmark("auto parts")
        assert bench["median_gross_margin"] == 0.22

    def test_with_hyphens(self):
        bench = get_benchmark("auto-parts")
        assert bench["median_gross_margin"] == 0.22


class TestGetBenchmarkUnknownSector:
    """get_benchmark falls back to defaults for unknown sectors."""

    def test_unknown_returns_default(self):
        bench = get_benchmark("nonexistent_sector_xyz")
        assert bench["median_gross_margin"] == 0.25
        assert bench["median_net_margin"] == 0.08
        assert bench["median_roe"] == 0.10
        assert bench["median_debt_ratio"] == 0.50

    def test_empty_string(self):
        bench = get_benchmark("")
        assert bench["median_gross_margin"] == 0.25


class TestRelativeScoreKnownSector:
    """relative_score computes correct scores for a known sector."""

    def test_above_median_metrics(self):
        """Company above industry medians should score above 50."""
        metrics = {
            "gross_margin": 0.55,   # > 0.45 tech median
            "net_margin": 0.18,     # > 0.12
            "roe": 0.20,            # > 0.14
            "debt_ratio": 0.20,     # < 0.35 (good)
            "revenue_growth": 0.25, # > 0.15
        }
        result = relative_score("technology", metrics)
        assert result["overall"] > 50
        assert result["scores"]["gross_margin"] > 50
        assert result["scores"]["net_margin"] > 50
        assert result["scores"]["debt_ratio"] > 50  # lower is better

    def test_below_median_metrics(self):
        """Company below industry medians should score below 50."""
        metrics = {
            "gross_margin": 0.20,   # < 0.45 tech median
            "net_margin": 0.05,     # < 0.12
            "roe": 0.07,            # < 0.14
            "debt_ratio": 0.60,     # > 0.35 (bad)
            "revenue_growth": 0.05, # < 0.15
        }
        result = relative_score("technology", metrics)
        assert result["overall"] < 50
        assert result["scores"]["gross_margin"] < 50
        assert result["scores"]["debt_ratio"] < 50  # higher is worse

    def test_exact_median(self):
        """Company exactly at median should score ~50."""
        metrics = {
            "gross_margin": 0.45,
            "net_margin": 0.12,
            "roe": 0.14,
            "debt_ratio": 0.35,
            "revenue_growth": 0.15,
        }
        result = relative_score("technology", metrics)
        for key, val in result["scores"].items():
            assert abs(val - 50.0) < 1.0, f"{key}: {val} != ~50"

    def test_pe_ratio_scoring(self):
        """PE at lower end of range → high score, at upper end → low score."""
        metrics_low_pe = {"pe_ratio": 20}  # below tech range (25, 60)
        result_low = relative_score("technology", metrics_low_pe)
        assert result_low["scores"]["pe_ratio"] == 100.0

        metrics_high_pe = {"pe_ratio": 80}  # above tech range
        result_high = relative_score("technology", metrics_high_pe)
        assert result_high["scores"]["pe_ratio"] == 0.0

        metrics_mid_pe = {"pe_ratio": 42.5}  # midpoint
        result_mid = relative_score("technology", metrics_mid_pe)
        assert abs(result_mid["scores"]["pe_ratio"] - 50.0) < 1.0

    def test_partial_metrics(self):
        """Only provided metrics are scored; overall is average of available."""
        metrics = {"gross_margin": 0.60}
        result = relative_score("technology", metrics)
        assert "gross_margin" in result["scores"]
        assert len(result["scores"]) == 1
        assert result["overall"] > 50

    def test_empty_metrics(self):
        """No metrics → overall defaults to 50."""
        result = relative_score("technology", {})
        assert result["overall"] == 50.0

    def test_benchmark_in_result(self):
        """Result includes the benchmark dict used."""
        result = relative_score("technology", {"gross_margin": 0.50})
        assert result["benchmark"]["median_gross_margin"] == 0.45


class TestRelativeScoreUnknownSector:
    """relative_score uses defaults for unknown sectors."""

    def test_unknown_sector_uses_default(self):
        metrics = {"gross_margin": 0.50}
        result = relative_score("unknown_sector_xyz", metrics)
        # default median_gross_margin is 0.25, so 0.50 → score > 50
        assert result["scores"]["gross_margin"] > 50
        assert result["benchmark"]["median_gross_margin"] == 0.25

    def test_all_sectors_in_benchmarks_dict(self):
        """All expected sectors have entries."""
        expected = [
            "technology", "consumer", "auto_parts", "internet",
            "healthcare", "finance", "manufacturing", "energy",
            "materials", "real_estate",
        ]
        for sector in expected:
            assert sector in INDUSTRY_BENCHMARKS
