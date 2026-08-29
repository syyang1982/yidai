"""Tests for the valuation analysis module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.valuation import score


class TestValuationAllPass:
    """All 3 checks pass => score=5.

    PE=16 < 100 PASS, percentile=0.35 < 0.70 PASS,
    PEG = 16/25 = 0.64 < 2.0 PASS (revenue_growth_rate=25 means 2500% base).
    """

    def test_score_is_5(self):
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 25,
        }
        result = score(data)
        assert result["score"] == 5

    def test_details_all_pass(self):
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 25,
        }
        result = score(data)
        # All scorable checks should pass; SKIP lines (e.g. peer_pe) don't have PASS
        pass_details = [d for d in result["details"] if "PASS" in d]
        skip_details = [d for d in result["details"] if "SKIP" in d]
        assert len(pass_details) == 2  # PE PASS + percentile PASS
        assert len(skip_details) == 4  # PEG SKIP + EV/EBITDA SKIP + peer_pe SKIP + ps_ratio SKIP
        # 1 company type + 2 PASS + 4 SKIP = 7
        assert len(result["details"]) == 7

    def test_peg_value_correct(self):
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 25,
        }
        result = score(data)
        peg_detail = [d for d in result["details"] if "peg" in d][0]
        # Growth company: PEG is already assessed in PE check, so SKIP
        assert "SKIP" in peg_detail


class TestValuationPEHigh:
    """PE=150 >= 100 but growth company: PEG=150/200=0.75 < 3 => PASS => score=5."""

    def test_score_is_4(self):
        data = {
            "pe_ratio": 150,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 200,  # PEG=150/200=0.75, passes PEG check
        }
        result = score(data)
        # Growth company with PE>=100: PEG=0.75 < 3 => PASS (high growth acceptable)
        assert result["score"] == 5

    def test_pe_fail_detail(self):
        data = {
            "pe_ratio": 150,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 200,
        }
        result = score(data)
        pe_detail = [d for d in result["details"] if "pe_ratio" in d][0]
        # Growth company: PE>=100 but PEG<3 => PASS
        assert "PASS" in pe_detail
        assert "150" in pe_detail


class TestValuationPEGFail:
    """PEG >= 2.0 (PE=30, growth_rate=10 => PEG=3.0) + high percentile => 2 failures => score=3."""

    def test_score_at_most_3(self):
        data = {
            "pe_ratio": 30,
            "pe_history_percentile": 0.80,
            "revenue_growth_rate": 10,
        }
        result = score(data)
        # percentile 0.80 >= 0.70 FAIL, PEG 30/10=3.0 >= 2.0 FAIL => 2 failures => score=3
        assert result["score"] <= 3

    def test_peg_value_in_details(self):
        data = {
            "pe_ratio": 30,
            "pe_history_percentile": 0.80,
            "revenue_growth_rate": 10,
        }
        result = score(data)
        peg_detail = [d for d in result["details"] if "peg" in d][0]
        assert "FAIL" in peg_detail
        # PEG = 30/10 = 3.0
        assert "3.00" in peg_detail

    def test_two_failures(self):
        data = {
            "pe_ratio": 30,
            "pe_history_percentile": 0.80,
            "revenue_growth_rate": 10,
        }
        result = score(data)
        fail_count = sum(1 for d in result["details"] if "FAIL" in d)
        assert fail_count == 2


class TestValuationPercentileNone:
    """pe_history_percentile=None => skipped, score based on remaining 2 checks."""

    def test_score_with_percentile_none(self):
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": None,
            "revenue_growth_rate": 25,
        }
        result = score(data)
        # PE=16 PASS, PEG=0.64 PASS => 2 checks, 0 failures => score=5
        assert result["score"] == 5

    def test_skip_detail_for_percentile(self):
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": None,
            "revenue_growth_rate": 25,
        }
        result = score(data)
        pct_detail = [d for d in result["details"] if "pe_history_percentile" in d][0]
        assert "SKIP" in pct_detail

    def test_only_two_checks_scored(self):
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": None,
            "revenue_growth_rate": 25,
        }
        result = score(data)
        skip_count = sum(1 for d in result["details"] if "SKIP" in d)
        pass_count = sum(1 for d in result["details"] if "PASS" in d)
        assert skip_count == 5  # percentile SKIP + PEG SKIP + EV/EBITDA SKIP + peer_pe SKIP + ps_ratio SKIP
        assert pass_count == 1  # only PE PASS (PE=16 < 100)


class TestValuationPeerComparison:
    """Test peer PE comparison check (Check 5)."""

    def test_peer_pass_when_cheaper(self):
        """Company PE below peer median => PASS."""
        data = {
            "pe_ratio": 18,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 10,
            "peer_median_pe": 22,
        }
        result = score(data)
        peer_detail = [d for d in result["details"] if "peer_pe" in d][0]
        assert "PASS" in peer_detail
        assert "便宜" in peer_detail

    def test_peer_pass_growth_premium(self):
        """Growth company with moderate premium => PASS."""
        data = {
            "pe_ratio": 30,
            "pe_history_percentile": None,
            "revenue_growth_rate": 25,  # growth company
            "peer_median_pe": 22,
        }
        result = score(data)
        peer_detail = [d for d in result["details"] if "peer_pe" in d][0]
        assert "PASS" in peer_detail
        assert "成长型可接受" in peer_detail

    def test_peer_fail_non_growth_premium(self):
        """Non-growth company with premium => FAIL."""
        data = {
            "pe_ratio": 35,
            "pe_history_percentile": None,
            "revenue_growth_rate": 5,  # not growth
            "peer_median_pe": 22,
        }
        result = score(data)
        peer_detail = [d for d in result["details"] if "peer_pe" in d][0]
        assert "FAIL" in peer_detail

    def test_peer_fail_significant_premium(self):
        """Any company with >50% premium => FAIL."""
        data = {
            "pe_ratio": 40,
            "pe_history_percentile": None,
            "revenue_growth_rate": 25,  # growth, but premium too high
            "peer_median_pe": 22,
        }
        result = score(data)
        peer_detail = [d for d in result["details"] if "peer_pe" in d][0]
        assert "FAIL" in peer_detail
        assert "显著溢价" in peer_detail

    def test_peer_skip_no_data(self):
        """No peer data => SKIP."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 25,
        }
        result = score(data)
        peer_detail = [d for d in result["details"] if "peer_pe" in d][0]
        assert "SKIP" in peer_detail


class TestPSRatio:
    """Test PS (Price-to-Sales) ratio check (Check 6)."""

    def test_ps_pass_attractive(self):
        """PS < 3 => PASS (有吸引力)."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 10,
            "ps_ratio": 2.5,
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "PASS" in ps_detail
        assert "有吸引力" in ps_detail

    def test_ps_pass_reasonable(self):
        """PS in [3, 6) => PASS (合理)."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 10,
            "ps_ratio": 4.5,
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "PASS" in ps_detail
        assert "合理" in ps_detail

    def test_ps_pass_growth_expensive(self):
        """PS in [6, 10) + growth => PASS (偏贵但成长型可接受)."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 25,  # growth company
            "ps_ratio": 8.0,
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "PASS" in ps_detail
        assert "成长型可接受" in ps_detail

    def test_ps_fail_non_growth_expensive(self):
        """PS in [6, 10) + non-growth => FAIL."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 5,  # not growth
            "ps_ratio": 8.0,
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "FAIL" in ps_detail
        assert "偏贵" in ps_detail

    def test_ps_fail_high(self):
        """PS >= 10 => FAIL (高估)."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 10,
            "ps_ratio": 15.0,
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "FAIL" in ps_detail
        assert "高估" in ps_detail

    def test_ps_skip_negative(self):
        """PS < 0 => SKIP (invalid data)."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 10,
            "ps_ratio": -1.5,
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "SKIP" in ps_detail

    def test_ps_skip_not_provided(self):
        """No ps_ratio => SKIP."""
        data = {
            "pe_ratio": 16,
            "pe_history_percentile": 0.35,
            "revenue_growth_rate": 10,
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "SKIP" in ps_detail


class TestB2BCompany:
    """Test B2B/SaaS industry awareness."""

    def test_b2b_uses_ps_when_pe_unavailable(self):
        """B2B company with PE unavailable: skips PE checks, uses PS."""
        data = {
            "pe_ratio": None,
            "pe_history_percentile": None,
            "revenue_growth_rate": 20,  # growth company
            "ps_ratio": 4.0,
            "industry": "saas",
        }
        result = score(data)
        # PE should be SKIP with B2B note
        pe_detail = [d for d in result["details"] if "pe_ratio" in d and "missing" in d.lower()][0]
        assert "B2B" in pe_detail
        assert "SKIP" in pe_detail
        # PS should be evaluated and PASS
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "PASS" in ps_detail
        # B2B type should be noted
        b2b_detail = [d for d in result["details"] if "B2B" in d][0]
        assert "saas" in b2b_detail

    def test_b2b_pe_available_uses_both(self):
        """B2B company with PE available: uses both PE and PS checks."""
        data = {
            "pe_ratio": -5,  # negative PE (unprofitable)
            "pe_history_percentile": None,
            "revenue_growth_rate": 30,  # growth company
            "ps_ratio": 5.0,
            "industry": "cloud",
        }
        result = score(data)
        # PE <= 0 but growth: SKIP (not a failure)
        pe_detail = [d for d in result["details"] if "pe_ratio" in d][0]
        assert "SKIP" in pe_detail
        # PS should also be evaluated
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "PASS" in ps_detail
        # B2B detected
        b2b_detail = [d for d in result["details"] if "B2B" in d][0]
        assert "cloud" in b2b_detail

    def test_b2b_flag_override(self):
        """is_b2b=True flag overrides industry detection."""
        data = {
            "pe_ratio": None,
            "pe_history_percentile": None,
            "revenue_growth_rate": 10,
            "ps_ratio": 2.0,
            "industry": "retail",  # not in B2B_INDUSTRIES
            "is_b2b": True,  # but flag says B2B
        }
        result = score(data)
        pe_detail = [d for d in result["details"] if "pe_ratio" in d and "missing" in d.lower()][0]
        assert "B2B" in pe_detail
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "PASS" in ps_detail

    def test_non_b2b_pe_missing_no_b2b_skip(self):
        """Non-B2B company with PE missing: normal SKIP (no B2B note)."""
        data = {
            "pe_ratio": None,
            "pe_history_percentile": None,
            "revenue_growth_rate": 10,
            "ps_ratio": 4.0,
            "industry": "retail",
        }
        result = score(data)
        pe_detail = [d for d in result["details"] if "pe_ratio" in d and "missing" in d.lower()][0]
        assert "B2B" not in pe_detail
        assert "SKIP" in pe_detail

    def test_b2b_semiconductor_industry(self):
        """Semiconductor is in B2B_INDUSTRIES."""
        data = {
            "pe_ratio": None,
            "pe_history_percentile": None,
            "revenue_growth_rate": 15,
            "ps_ratio": 3.5,
            "industry": "semiconductor",
        }
        result = score(data)
        b2b_detail = [d for d in result["details"] if "B2B" in d][0]
        assert "semiconductor" in b2b_detail

    def test_b2b_ps_fail_high_valuation(self):
        """B2B company with very high PS => FAIL."""
        data = {
            "pe_ratio": None,
            "pe_history_percentile": None,
            "revenue_growth_rate": 10,
            "ps_ratio": 12.0,
            "industry": "biotech",
        }
        result = score(data)
        ps_detail = [d for d in result["details"] if "ps_ratio" in d][0]
        assert "FAIL" in ps_detail
        assert "高估" in ps_detail
