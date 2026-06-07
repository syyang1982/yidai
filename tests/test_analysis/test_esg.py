"""Tests for the simplified ESG (governance) scoring module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.esg import score_governance


def _find_detail(details: list[str], keyword: str) -> str:
    """Find the first detail line containing *keyword*."""
    return [d for d in details if keyword in d][0]


class TestGovernanceAllPass:
    """All four indicators at best values → score 5."""

    def test_score_is_5(self):
        data = {
            "related_party_transactions": 0.0,
            "independent_director_ratio": 0.5,
            "audit_opinion": "unqualified",
            "insider_ownership_pct": 15.0,
        }
        result = score_governance(data)
        assert result["score"] == 5

    def test_details_all_pass(self):
        data = {
            "related_party_transactions": 0.0,
            "independent_director_ratio": 0.5,
            "audit_opinion": "unqualified",
            "insider_ownership_pct": 15.0,
        }
        result = score_governance(data)
        pass_count = sum(1 for d in result["details"] if "PASS" in d)
        assert pass_count == 4

    def test_has_details_list(self):
        result = score_governance({})
        assert isinstance(result["details"], list)
        assert len(result["details"]) == 4


class TestGovernanceAllMissing:
    """All fields missing → neutral score 3."""

    def test_score_is_3(self):
        result = score_governance({})
        assert result["score"] == 3

    def test_details_all_skip(self):
        result = score_governance({})
        skip_count = sum(1 for d in result["details"] if "SKIP" in d)
        assert skip_count == 4


class TestGovernanceRPT:
    """Related-party transactions scoring."""

    def test_zero_rpt(self):
        result = score_governance({"related_party_transactions": 0.0})
        detail = _find_detail(result["details"], "related_party")
        assert "PASS" in detail
        assert "无关联交易" in detail

    def test_low_rpt(self):
        result = score_governance({"related_party_transactions": 0.02})
        detail = _find_detail(result["details"], "related_party")
        assert "PASS" in detail

    def test_medium_rpt(self):
        result = score_governance({"related_party_transactions": 0.05})
        detail = _find_detail(result["details"], "related_party")
        assert "NEUTRAL" in detail

    def test_high_rpt(self):
        result = score_governance({"related_party_transactions": 0.15})
        detail = _find_detail(result["details"], "related_party")
        assert "FAIL" in detail
        assert "关注" in detail


class TestGovernanceIndependentDirectors:
    """Independent director ratio scoring."""

    def test_high_ratio(self):
        result = score_governance({"independent_director_ratio": 0.6})
        detail = _find_detail(result["details"], "independent_director")
        assert "PASS" in detail
        assert "优秀" in detail

    def test_compliant_ratio(self):
        result = score_governance({"independent_director_ratio": 0.35})
        detail = _find_detail(result["details"], "independent_director")
        assert "PASS" in detail
        assert "合规" in detail

    def test_low_ratio(self):
        result = score_governance({"independent_director_ratio": 0.30})
        detail = _find_detail(result["details"], "independent_director")
        assert "FAIL" in detail
        assert "偏低" in detail

    def test_very_low_ratio(self):
        result = score_governance({"independent_director_ratio": 0.20})
        detail = _find_detail(result["details"], "independent_director")
        assert "FAIL" in detail
        assert "严重不足" in detail


class TestGovernanceAuditOpinion:
    """Audit opinion scoring."""

    def test_unqualified(self):
        result = score_governance({"audit_opinion": "unqualified"})
        detail = _find_detail(result["details"], "audit_opinion")
        assert "PASS" in detail

    def test_qualified(self):
        result = score_governance({"audit_opinion": "qualified"})
        detail = _find_detail(result["details"], "audit_opinion")
        assert "FAIL" in detail

    def test_adverse(self):
        result = score_governance({"audit_opinion": "adverse"})
        detail = _find_detail(result["details"], "audit_opinion")
        assert "FAIL" in detail
        assert "否定意见" in detail

    def test_emphasis(self):
        result = score_governance({"audit_opinion": "emphasis"})
        detail = _find_detail(result["details"], "audit_opinion")
        assert "NEUTRAL" in detail

    def test_unknown_opinion(self):
        result = score_governance({"audit_opinion": "disclaimer"})
        detail = _find_detail(result["details"], "audit_opinion")
        assert "SKIP" in detail

    def test_case_insensitive(self):
        result = score_governance({"audit_opinion": "Unqualified"})
        detail = _find_detail(result["details"], "audit_opinion")
        assert "PASS" in detail


class TestGovernanceInsiderOwnership:
    """Insider ownership percentage scoring."""

    def test_moderate_ownership(self):
        result = score_governance({"insider_ownership_pct": 20.0})
        detail = _find_detail(result["details"], "insider_ownership")
        assert "PASS" in detail
        assert "适度" in detail

    def test_low_ownership(self):
        result = score_governance({"insider_ownership_pct": 3.0})
        detail = _find_detail(result["details"], "insider_ownership")
        assert "NEUTRAL" in detail
        assert "偏低" in detail

    def test_high_but_acceptable(self):
        result = score_governance({"insider_ownership_pct": 40.0})
        detail = _find_detail(result["details"], "insider_ownership")
        assert "NEUTRAL" in detail
        assert "偏高" in detail

    def test_excessive_ownership(self):
        result = score_governance({"insider_ownership_pct": 60.0})
        detail = _find_detail(result["details"], "insider_ownership")
        assert "FAIL" in detail
        assert "过度集中" in detail


class TestGovernanceMixed:
    """Mix of pass, fail, and missing → composite score."""

    def test_mixed_score(self):
        data = {
            "related_party_transactions": 0.0,       # 5
            "independent_director_ratio": 0.20,       # 1
            "audit_opinion": "unqualified",           # 5
            "insider_ownership_pct": 60.0,            # 2
        }
        result = score_governance(data)
        # avg = (5 + 1 + 5 + 2) / 4 = 3.25 → round = 3
        assert result["score"] == 3

    def test_mostly_pass(self):
        data = {
            "related_party_transactions": 0.02,       # 4
            "independent_director_ratio": 0.5,        # 5
            "audit_opinion": "unqualified",           # 5
            "insider_ownership_pct": 15.0,            # 5
        }
        result = score_governance(data)
        # avg = (4 + 5 + 5 + 5) / 4 = 4.75 → round = 5
        assert result["score"] == 5

    def test_mostly_fail(self):
        data = {
            "related_party_transactions": 0.20,       # 1
            "independent_director_ratio": 0.15,       # 1
            "audit_opinion": "adverse",               # 0
            "insider_ownership_pct": 70.0,            # 2
        }
        result = score_governance(data)
        # avg = (1 + 1 + 0 + 2) / 4 = 1.0 → round = 1
        assert result["score"] == 1

    def test_partial_data(self):
        """Only some fields provided → others default to 3."""
        data = {
            "audit_opinion": "qualified",  # 2
        }
        result = score_governance(data)
        # avg = (3 + 3 + 2 + 3) / 4 = 2.75 → round = 3
        assert result["score"] == 3
