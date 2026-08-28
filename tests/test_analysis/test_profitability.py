"""Tests for the profitability analysis module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.profitability import score


class TestProfitabilityAllPass:
    """All 4 checks pass => score=5."""

    def test_score_is_5(self):
        data = {
            "revenue_growth": 0.25,
            "gross_margin": 0.22,
            "net_margin": 0.09,
            "roe": 0.18,
        }
        result = score(data)
        assert result["score"] == 5

    def test_details_all_pass(self):
        data = {
            "revenue_growth": 0.25,
            "gross_margin": 0.22,
            "net_margin": 0.09,
            "roe": 0.18,
        }
        result = score(data)
        pass_details = [d for d in result["details"] if "PASS" in d]
        skip_details = [d for d in result["details"] if "SKIP" in d]
        assert len(pass_details) == 4
        assert len(skip_details) == 1  # profit quality SKIP (no net_income_growth)
        assert len(result["details"]) == 5


class TestProfitabilityOneFail:
    """1 check fails (ROE=0.05 < 0.10) => score=4."""

    def test_score_is_4(self):
        data = {
            "revenue_growth": 0.25,
            "gross_margin": 0.22,
            "net_margin": 0.09,
            "roe": 0.05,
        }
        result = score(data)
        assert result["score"] == 4

    def test_roe_fails(self):
        data = {
            "revenue_growth": 0.25,
            "gross_margin": 0.22,
            "net_margin": 0.09,
            "roe": 0.05,
        }
        result = score(data)
        roe_detail = [d for d in result["details"] if "roe" in d][0]
        assert "FAIL" in roe_detail
        assert "5.00%" in roe_detail


class TestProfitabilityTwoFail:
    """2 checks fail (ROE=0.05, net_margin=0.03) => score=3."""

    def test_score_is_3(self):
        data = {
            "revenue_growth": 0.25,
            "gross_margin": 0.22,
            "net_margin": 0.03,
            "roe": 0.05,
        }
        result = score(data)
        assert result["score"] == 3

    def test_two_failures_in_details(self):
        data = {
            "revenue_growth": 0.25,
            "gross_margin": 0.22,
            "net_margin": 0.03,
            "roe": 0.05,
        }
        result = score(data)
        fail_count = sum(1 for d in result["details"] if "FAIL" in d)
        assert fail_count == 2


class TestProfitabilityAllFail:
    """All 4 checks fail => score=0."""

    def test_score_is_0(self):
        data = {
            "revenue_growth": 0.01,
            "gross_margin": 0.05,
            "net_margin": 0.01,
            "roe": 0.02,
        }
        result = score(data)
        assert result["score"] == 0

    def test_all_fail_in_details(self):
        data = {
            "revenue_growth": 0.01,
            "gross_margin": 0.05,
            "net_margin": 0.01,
            "roe": 0.02,
        }
        result = score(data)
        fail_details = [d for d in result["details"] if "FAIL" in d]
        skip_details = [d for d in result["details"] if "SKIP" in d]
        assert len(fail_details) == 4
        assert len(skip_details) == 1  # profit quality SKIP (no net_income_growth)


class TestProfitabilityDetailsContainValues:
    """Details should contain the actual numeric values passed in."""

    def test_details_show_actual_values(self):
        data = {
            "revenue_growth": 0.1234,
            "gross_margin": 0.5678,
            "net_margin": 0.0901,
            "roe": 0.2345,
        }
        result = score(data)
        combined = " ".join(result["details"])
        # Values are formatted as percentages
        assert "12.34%" in combined
        assert "56.78%" in combined
        assert "9.01%" in combined
        assert "23.45%" in combined
