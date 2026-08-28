"""Tests for the cash flow analysis module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.cashflow import score


class TestCashflowAllPassImprovingTrend:
    """All 3 checks pass + OCF trend improving => score=5."""

    def test_score_is_5(self):
        data = {
            "operating_cash_flow": 1000,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
            "ocf_current": 1200,
            "ocf_previous": 1000,
        }
        result = score(data)
        assert result["score"] == 5

    def test_details_all_pass(self):
        data = {
            "operating_cash_flow": 1000,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
            "ocf_current": 1200,
            "ocf_previous": 1000,
        }
        result = score(data)
        pass_count = sum(1 for d in result["details"] if "PASS" in d)
        assert pass_count == 3
        # Trend should show OK
        trend_detail = [d for d in result["details"] if "trend" in d.lower()][0]
        assert "OK" in trend_detail


class TestCashflowAllPassDecliningTrend:
    """All 3 checks pass but OCF trend declining => score=4."""

    def test_score_is_4(self):
        data = {
            "operating_cash_flow": 1000,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
            "ocf_current": 800,
            "ocf_previous": 1000,
        }
        result = score(data)
        assert result["score"] == 4

    def test_trend_warning(self):
        data = {
            "operating_cash_flow": 1000,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
            "ocf_current": 800,
            "ocf_previous": 1000,
        }
        result = score(data)
        trend_detail = [d for d in result["details"] if "trend" in d.lower()][0]
        assert "WARNING" in trend_detail
        assert "declining" in trend_detail


class TestCashflowOCFNegative:
    """OCF negative => at least 1 failure => score <= 3."""

    def test_score_at_most_3(self):
        data = {
            "operating_cash_flow": -100,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
            "ocf_current": 1200,
            "ocf_previous": 1000,
        }
        result = score(data)
        assert result["score"] <= 3

    def test_ocf_fail_detail(self):
        data = {
            "operating_cash_flow": -100,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
        }
        result = score(data)
        ocf_detail = [d for d in result["details"] if "operating_cash_flow" in d][0]
        assert "FAIL" in ocf_detail
        assert "-100" in ocf_detail


class TestCashflowAllFail:
    """All 3 checks fail => 3 failures => score=0."""

    def test_score_is_0(self):
        data = {
            "operating_cash_flow": -100,
            "ocf_to_ni_ratio": 0.3,
            "free_cash_flow": -50,
        }
        result = score(data)
        assert result["score"] == 0

    def test_all_fail_details(self):
        data = {
            "operating_cash_flow": -100,
            "ocf_to_ni_ratio": 0.3,
            "free_cash_flow": -50,
        }
        result = score(data)
        fail_count = sum(1 for d in result["details"] if "FAIL" in d)
        assert fail_count == 3


class TestCashflowNoTrendData:
    """No trend data provided => trend skipped, score based on checks only."""

    def test_score_without_trend(self):
        data = {
            "operating_cash_flow": 1000,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
        }
        result = score(data)
        # All 3 pass, trend skipped (trend_ok stays True) => score=5
        assert result["score"] == 5

    def test_trend_skip_detail(self):
        data = {
            "operating_cash_flow": 1000,
            "ocf_to_ni_ratio": 0.9,
            "free_cash_flow": 500,
        }
        result = score(data)
        trend_detail = [d for d in result["details"] if "trend" in d.lower()][0]
        assert "SKIP" in trend_detail
