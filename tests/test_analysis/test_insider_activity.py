"""Tests for the insider activity detection module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.insider_activity import (
    check_insider_activity,
    format_insider_warnings,
    _classify_reduction,
    _classify_issuance,
)


# ---------------------------------------------------------------------------
# _classify_reduction
# ---------------------------------------------------------------------------

class TestClassifyReduction:
    def test_major_large_reduction_is_high(self):
        assert _classify_reduction("major", 1.5, None) == "high"

    def test_major_small_reduction_is_medium(self):
        assert _classify_reduction("major", 0.3, None) == "medium"

    def test_major_no_pct_is_medium(self):
        assert _classify_reduction("控股股东", None, None) == "medium"

    def test_executive_is_medium(self):
        assert _classify_reduction("executive", 0.1, None) == "medium"

    def test_executive_cn_is_medium(self):
        assert _classify_reduction("高管", 2.0, None) == "medium"

    def test_institutional_small_is_low(self):
        assert _classify_reduction("institutional", 0.1, None) == "low"

    def test_institutional_large_is_medium(self):
        assert _classify_reduction("institutional", 0.8, None) == "medium"


# ---------------------------------------------------------------------------
# _classify_issuance
# ---------------------------------------------------------------------------

class TestClassifyIssuance:
    def test_private_placement_is_high(self):
        assert _classify_issuance("定增", 1e9) == "high"

    def test_rights_issue_is_medium(self):
        assert _classify_issuance("配股", 5e8) == "medium"

    def test_convertible_bond_is_medium(self):
        assert _classify_issuance("可转债", 1e9) == "medium"

    def test_public_offering_is_low(self):
        assert _classify_issuance("公开增发", 2e9) == "low"


# ---------------------------------------------------------------------------
# check_insider_activity — empty / no events
# ---------------------------------------------------------------------------

class TestCheckInsiderActivityEmpty:
    def test_empty_events_no_warning(self):
        result = check_insider_activity([])
        assert result["has_warning"] is False
        assert result["severity"] == "none"
        assert result["warnings"] == []

    def test_none_events_no_warning(self):
        result = check_insider_activity(None)
        assert result["has_warning"] is False

    def test_old_events_ignored(self):
        """Events older than lookback_days should be filtered out."""
        events = [
            {
                "event_type": "reduction",
                "date": "2020-01-01",  # very old
                "holder_type": "major",
                "holder_name": "控股股东A",
                "shares_traded": -1000000,
                "shares_pct": 2.0,
                "amount": 5e7,
            }
        ]
        result = check_insider_activity(events, lookback_days=30)
        assert result["has_warning"] is False


# ---------------------------------------------------------------------------
# check_insider_activity — reductions
# ---------------------------------------------------------------------------

class TestCheckInsiderActivityReductions:
    def test_major_reduction_generates_high_warning(self):
        events = [
            {
                "event_type": "reduction",
                "date": "2026-06-01",
                "holder_type": "major",
                "holder_name": "控股股东张某",
                "shares_traded": -5000000,
                "shares_pct": 1.5,
                "amount": 2.5e8,
            }
        ]
        result = check_insider_activity(events, lookback_days=365)
        assert result["has_warning"] is True
        assert result["severity"] == "high"
        assert len(result["warnings"]) == 1
        assert "重大减持" in result["warnings"][0]
        assert result["summary"]["reductions"] == 1

    def test_executive_reduction_generates_medium_warning(self):
        events = [
            {
                "event_type": "reduction",
                "date": "2026-05-15",
                "holder_type": "executive",
                "holder_name": "财务总监李某",
                "shares_traded": -100000,
                "shares_pct": 0.05,
                "amount": 5e6,
            }
        ]
        result = check_insider_activity(events, lookback_days=365)
        assert result["has_warning"] is True
        assert result["severity"] == "medium"
        assert "减持" in result["warnings"][0]

    def test_multiple_reductions_highest_severity_wins(self):
        events = [
            {
                "event_type": "reduction",
                "date": "2026-06-01",
                "holder_type": "executive",
                "holder_name": "董事王某",
                "shares_traded": -50000,
                "shares_pct": 0.02,
                "amount": 2e6,
            },
            {
                "event_type": "reduction",
                "date": "2026-06-10",
                "holder_type": "major",
                "holder_name": "控股股东",
                "shares_traded": -3000000,
                "shares_pct": 2.0,
                "amount": 1.5e8,
            },
        ]
        result = check_insider_activity(events, lookback_days=365)
        assert result["has_warning"] is True
        assert result["severity"] == "high"
        assert result["summary"]["reductions"] == 2


# ---------------------------------------------------------------------------
# check_insider_activity — issuances
# ---------------------------------------------------------------------------

class TestCheckInsiderActivityIssuances:
    def test_private_placement_high_warning(self):
        events = [
            {
                "event_type": "issuance",
                "date": "2026-04-01",
                "issuance_type": "定增",
                "amount": 5e9,
                "shares_pct": 5.0,
                "holder_name": "上市公司定增",
            }
        ]
        result = check_insider_activity(events, lookback_days=365)
        assert result["has_warning"] is True
        assert result["severity"] == "high"
        assert "定向增发" in result["warnings"][0]
        assert result["summary"]["issuances"] == 1

    def test_rights_issue_medium_warning(self):
        events = [
            {
                "event_type": "issuance",
                "date": "2026-03-01",
                "issuance_type": "配股",
                "amount": 1e9,
                "holder_name": "上市公司配股",
            }
        ]
        result = check_insider_activity(events, lookback_days=365)
        assert result["has_warning"] is True
        assert result["severity"] == "medium"


# ---------------------------------------------------------------------------
# check_insider_activity — buybacks (positive counter-signal)
# ---------------------------------------------------------------------------

class TestCheckInsiderActivityBuybacks:
    def test_buyback_generates_positive_note(self):
        events = [
            {
                "event_type": "buyback",
                "date": "2026-06-01",
                "amount": 2e9,
                "holder_name": "公司回购",
            }
        ]
        result = check_insider_activity(events, lookback_days=365)
        # buyback is NOT a warning
        assert result["has_warning"] is False
        assert result["severity"] == "none"
        assert len(result["warnings"]) == 1
        assert "✅" in result["warnings"][0]
        assert "回购" in result["warnings"][0]

    def test_buyback_with_reduction_mixed(self):
        """Buyback + reduction: has_warning=True (reduction takes priority)."""
        events = [
            {
                "event_type": "buyback",
                "date": "2026-06-01",
                "amount": 1e9,
                "holder_name": "公司回购",
            },
            {
                "event_type": "reduction",
                "date": "2026-06-10",
                "holder_type": "major",
                "holder_name": "控股股东",
                "shares_traded": -2000000,
                "shares_pct": 1.5,
                "amount": 1e8,
            },
        ]
        result = check_insider_activity(events, lookback_days=365)
        assert result["has_warning"] is True
        assert result["severity"] == "high"
        assert result["summary"]["reductions"] == 1
        assert result["summary"]["buybacks"] == 1


# ---------------------------------------------------------------------------
# format_insider_warnings
# ---------------------------------------------------------------------------

class TestFormatInsiderWarnings:
    def test_no_warning_returns_empty(self):
        result = {"has_warning": False, "severity": "none", "warnings": []}
        assert format_insider_warnings(result) == ""

    def test_high_severity_shows_red_emoji(self):
        result = {
            "has_warning": True,
            "severity": "high",
            "warnings": ["⚠️ 重大减持: 控股股东减持 1.50%"],
            "summary": {"reductions": 1, "issuances": 0, "buybacks": 0},
        }
        output = format_insider_warnings(result)
        assert "🔴" in output
        assert "重大减持" in output
        assert "减持1笔" in output

    def test_medium_severity_shows_yellow_emoji(self):
        result = {
            "has_warning": True,
            "severity": "medium",
            "warnings": ["⚠️ 减持: 高管减持"],
            "summary": {"reductions": 1, "issuances": 0, "buybacks": 0},
        }
        output = format_insider_warnings(result)
        assert "🟡" in output

    def test_mixed_summary_display(self):
        result = {
            "has_warning": True,
            "severity": "high",
            "warnings": ["⚠️ 重大减持", "⚠️ 定向增发"],
            "summary": {"reductions": 2, "issuances": 1, "buybacks": 0},
        }
        output = format_insider_warnings(result)
        assert "减持2笔" in output
        assert "增发1笔" in output


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unparseable_date_skipped(self):
        events = [
            {
                "event_type": "reduction",
                "date": "not-a-date",
                "holder_type": "major",
                "holder_name": "test",
            }
        ]
        result = check_insider_activity(events)
        assert result["has_warning"] is False

    def test_missing_fields_handled(self):
        """Events with missing optional fields should not crash."""
        events = [
            {
                "event_type": "reduction",
                "date": "2026-06-01",
                # holder_type, shares_pct, amount all missing
            }
        ]
        result = check_insider_activity(events)
        assert result["has_warning"] is True
        assert result["severity"] == "low"  # defaults to low without type info

    def test_unknown_event_type_ignored(self):
        events = [
            {
                "event_type": "dividend",
                "date": "2026-06-01",
                "amount": 1e8,
            }
        ]
        result = check_insider_activity(events)
        # Unknown types are not reductions/issuances/buybacks
        assert result["has_warning"] is False
