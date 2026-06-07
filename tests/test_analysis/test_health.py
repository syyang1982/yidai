"""Tests for the financial health analysis module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.health import score


class TestHealthAllPass:
    """All 3 checks pass => score=5."""

    def test_score_is_5(self):
        data = {
            "debt_ratio": 0.40,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        assert result["score"] == 5

    def test_details_all_pass(self):
        data = {
            "debt_ratio": 0.40,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        pass_details = [d for d in result["details"] if "PASS" in d]
        skip_details = [d for d in result["details"] if "SKIP" in d]
        assert len(pass_details) == 3
        assert len(skip_details) == 1  # debt_to_equity missing => SKIP
        assert len(result["details"]) == 4


class TestHealthDebtRatioFail:
    """debt_ratio=0.80 >= 0.70 => 1 failure => score=4."""

    def test_score_is_4(self):
        data = {
            "debt_ratio": 0.80,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        assert result["score"] == 4

    def test_debt_ratio_fail_detail(self):
        data = {
            "debt_ratio": 0.80,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        debt_detail = [d for d in result["details"] if "debt_ratio:" in d and "interest" not in d][0]
        assert "FAIL" in debt_detail
        assert "80.00%" in debt_detail


class TestHealthMissingCurrentRatio:
    """Missing current_ratio => skipped, only 2 checks counted, both pass => score=5."""

    def test_score_with_missing_current_ratio(self):
        data = {
            "debt_ratio": 0.40,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        # Both remaining checks pass => 0 failures out of 2 => score=5
        assert result["score"] == 5

    def test_skip_detail_present(self):
        data = {
            "debt_ratio": 0.40,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        current_ratio_detail = [d for d in result["details"] if "current_ratio" in d][0]
        assert "SKIP" in current_ratio_detail

    def test_total_checks_reduced(self):
        """With current_ratio missing, only 2 checks are scored."""
        data = {
            "debt_ratio": 0.40,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        # 2 pass details + 1 skip detail = 3 total
        skip_count = sum(1 for d in result["details"] if "SKIP" in d)
        pass_count = sum(1 for d in result["details"] if "PASS" in d)
        assert skip_count == 2  # current_ratio + debt_to_equity both SKIP
        assert pass_count == 2


class TestHealthAllFail:
    """All 3 checks fail => 3 failures => score=1."""

    def test_score_is_1(self):
        data = {
            "debt_ratio": 0.80,
            "current_ratio": 0.5,
            "interest_bearing_debt_ratio": 0.50,
        }
        result = score(data)
        assert result["score"] == 1

    def test_all_fail_in_details(self):
        data = {
            "debt_ratio": 0.80,
            "current_ratio": 0.5,
            "interest_bearing_debt_ratio": 0.50,
        }
        result = score(data)
        fail_details = [d for d in result["details"] if "FAIL" in d]
        skip_details = [d for d in result["details"] if "SKIP" in d]
        warning_details = [d for d in result["details"] if "高负债率" in d]
        assert len(fail_details) == 3
        assert len(skip_details) == 1  # debt_to_equity missing
        assert len(warning_details) == 1  # debt_ratio > 60% warning


# --- W3.2: Multi-period trend tests ---


class TestHealthTrendDeteriorating:
    """debt_ratio increasing across periods => -1 penalty."""

    def test_deteriorating_penalty(self):
        data = {
            "debt_ratio": 0.50,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        # All pass => score=5; previous debt_ratio=0.40, now 0.50 => deteriorating => -1
        previous = {"debt_ratio": 0.40}
        result = score(data, previous_data=previous)
        assert result["score"] == 4
        assert any("趋势恶化" in d for d in result["details"])

    def test_deteriorating_penalty_floors_at_zero(self):
        data = {
            "debt_ratio": 0.80,
            "current_ratio": 0.5,
            "interest_bearing_debt_ratio": 0.50,
        }
        # All fail => score=1; deteriorating => -1 => 0
        previous = {"debt_ratio": 0.70}
        result = score(data, previous_data=previous)
        assert result["score"] == 0


class TestHealthTrendImproving:
    """debt_ratio decreasing => no extra penalty (score on current state)."""

    def test_improving_no_penalty(self):
        data = {
            "debt_ratio": 0.40,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        previous = {"debt_ratio": 0.50}
        result = score(data, previous_data=previous)
        assert result["score"] == 5  # no penalty
        assert any("趋势改善" in d for d in result["details"])


class TestHealthTrendNoPrevious:
    """No previous_data => no trend analysis, backward compatible."""

    def test_no_previous_data_backward_compat(self):
        data = {
            "debt_ratio": 0.40,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data)
        assert result["score"] == 5
        assert not any("趋势" in d for d in result["details"])

    def test_previous_data_none_explicit(self):
        data = {
            "debt_ratio": 0.40,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data, previous_data=None)
        assert result["score"] == 5
        assert not any("趋势" in d for d in result["details"])

    def test_previous_data_missing_debt_ratio(self):
        """previous_data present but missing debt_ratio => no trend analysis."""
        data = {
            "debt_ratio": 0.50,
            "current_ratio": 2.0,
            "interest_bearing_debt_ratio": 0.15,
        }
        result = score(data, previous_data={"current_ratio": 1.5})
        assert result["score"] == 5  # all pass, no trend penalty
        assert not any("趋势" in d for d in result["details"])
