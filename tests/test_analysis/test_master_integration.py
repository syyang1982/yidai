"""Tests for the multi-master investment framework integration module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.master_integration import (
    classify_lynch_type,
    calculate_peg,
    graham_pe_x_pb,
    greenblatt_assessment,
    duanyongping_checklist,
    generate_premortem_questions,
    integrated_assessment,
    format_integrated_assessment,
)


# ---------------------------------------------------------------------------
# Lynch Classification
# ---------------------------------------------------------------------------

class TestLynchClassification:
    def test_fast_grower(self):
        scores = {"growth": 5, "health": 3, "valuation": 3, "dividend": 1, "profitability": 4}
        result = classify_lynch_type(scores)
        assert result["category"] == "快速增长型"
        assert result["tenbagger_potential"] is True

    def test_stalwart(self):
        scores = {"growth": 3, "health": 4, "valuation": 3, "dividend": 3, "profitability": 4}
        result = classify_lynch_type(scores)
        assert result["category"] == "稳健增长型"
        assert result["tenbagger_potential"] is False

    def test_slow_grower(self):
        scores = {"growth": 1, "health": 3, "valuation": 3, "dividend": 4, "profitability": 3}
        result = classify_lynch_type(scores)
        assert result["category"] == "缓慢增长型"

    def test_turnaround(self):
        scores = {"growth": 2, "health": 1, "valuation": 3, "dividend": 0, "profitability": 3}
        result = classify_lynch_type(scores)
        assert result["category"] == "困境反转型"
        assert result["tenbagger_potential"] is True

    def test_unclassified(self):
        scores = {"growth": 2, "health": 3, "valuation": 3, "dividend": 2, "profitability": 2}
        result = classify_lynch_type(scores)
        assert result["category"] == "待分类"


# ---------------------------------------------------------------------------
# PEG Calculation
# ---------------------------------------------------------------------------

class TestPEG:
    def test_undervalued(self):
        result = calculate_peg(15, 30)
        assert result["peg"] == 0.5
        assert result["rating"] == "合理偏低"

    def test_deeply_undervalued(self):
        result = calculate_peg(10, 40)
        assert result["peg"] == 0.25
        assert result["rating"] == "严重低估"

    def test_overvalued(self):
        result = calculate_peg(50, 10)
        assert result["peg"] == 5.0
        assert result["rating"] == "高估"

    def test_no_pe(self):
        result = calculate_peg(None, 20)
        assert result["peg"] is None

    def test_negative_growth(self):
        result = calculate_peg(15, -5)
        assert result["peg"] is None

    def test_fallback_to_earnings(self):
        result = calculate_peg(20, None, 15)
        assert result["peg"] is not None
        assert result["source"] == "earnings"


# ---------------------------------------------------------------------------
# Graham PE×PB
# ---------------------------------------------------------------------------

class TestGrahamPEPB:
    def test_deep_value(self):
        result = graham_pe_x_pb(8, 1.0)
        assert result["passes"] is True
        assert result["pe_x_pb"] == 8.0
        assert "深度" in result["rating"]

    def test_passes(self):
        result = graham_pe_x_pb(12, 1.5)
        assert result["passes"] is True
        assert result["pe_x_pb"] == 18.0

    def test_fails(self):
        result = graham_pe_x_pb(25, 2.0)
        assert result["passes"] is False
        assert result["pe_x_pb"] == 50.0

    def test_missing_data(self):
        result = graham_pe_x_pb(None, 1.5)
        assert result["passes"] is None


# ---------------------------------------------------------------------------
# Greenblatt Magic Formula
# ---------------------------------------------------------------------------

class TestGreenblatt:
    def test_both_pass(self):
        result = greenblatt_assessment(ebit=120, ev=1000, invested_capital=500)
        # ROIC = 120*0.75/500 = 18% ✅, EY = 120/1000 = 12% ✅
        assert result["roic_pass"] is True
        assert result["ey_pass"] is True
        assert "好公司" in result["rating"]

    def test_only_roic_passes(self):
        result = greenblatt_assessment(ebit=120, ev=2000, invested_capital=500)
        # ROIC = 18% ✅, EY = 6% ❌
        assert result["roic_pass"] is True
        assert result["ey_pass"] is False
        assert "偏贵" in result["rating"]

    def test_missing_data(self):
        result = greenblatt_assessment(ebit=None, ev=None, invested_capital=None)
        assert result["roic"] is None
        assert result["earnings_yield"] is None


# ---------------------------------------------------------------------------
# 段永平 三维评估
# ---------------------------------------------------------------------------

class TestDuanyongping:
    def test_all_good(self):
        scores = {
            "profitability": 5, "growth": 4, "cashflow": 4,
            "health": 4, "ownership": 4, "strategy": 4,
            "valuation": 4, "dividend": 3,
        }
        result = duanyongping_checklist(scores)
        assert result["good_business"] >= 4
        assert "强烈推荐" in result["verdict"]

    def test_good_business_bad_price(self):
        scores = {
            "profitability": 5, "growth": 4, "cashflow": 4,
            "health": 4, "ownership": 4, "strategy": 4,
            "valuation": 1, "dividend": 1,
        }
        result = duanyongping_checklist(scores)
        assert "等待好价格" in result["verdict"]

    def test_bad_business(self):
        scores = {
            "profitability": 1, "growth": 1, "cashflow": 1,
            "health": 3, "ownership": 3, "strategy": 3,
            "valuation": 4, "dividend": 3,
        }
        result = duanyongping_checklist(scores)
        assert "生意模式" in result["verdict"]


# ---------------------------------------------------------------------------
# Pre-mortem
# ---------------------------------------------------------------------------

class TestPremortem:
    def test_basic_questions(self):
        scores = {"valuation": 3, "growth": 3, "health": 3, "cashflow": 3}
        questions = generate_premortem_questions(scores)
        assert len(questions) >= 5
        assert any("亏损50%" in q for q in questions)

    def test_high_growth_specific(self):
        scores = {"valuation": 3, "growth": 5, "health": 3, "cashflow": 3}
        questions = generate_premortem_questions(scores)
        assert any("高增长" in q or "增长" in q for q in questions)

    def test_turnaround_specific(self):
        scores = {"valuation": 3, "growth": 2, "health": 1, "cashflow": 3}
        lynch = {"category": "困境反转型"}
        questions = generate_premortem_questions(scores, lynch)
        assert any("困境" in q for q in questions)

    def test_low_valuation_trap(self):
        scores = {"valuation": 5, "growth": 2, "health": 3, "cashflow": 3}
        questions = generate_premortem_questions(scores)
        assert any("价值陷阱" in q for q in questions)


# ---------------------------------------------------------------------------
# Integrated Assessment
# ---------------------------------------------------------------------------

class TestIntegratedAssessment:
    def test_strong_buy(self):
        scores = {
            "profitability": 5, "health": 4, "cashflow": 4,
            "valuation": 4, "growth": 4, "dividend": 3,
            "ownership": 4, "strategy": 4,
        }
        result = integrated_assessment(
            scores,
            financial_data={"revenue_growth_rate": 30},
            price_data={"pe_ratio": 15, "pb_ratio": 1.2},
        )
        assert "买入" in result["verdict"] or "强烈" in result["verdict"]
        assert result["yidai_total"] == 32

    def test_dealbreaker_low_health(self):
        scores = {
            "profitability": 3, "health": 1, "cashflow": 3,
            "valuation": 3, "growth": 3, "dividend": 3,
            "ownership": 3, "strategy": 3,
        }
        result = integrated_assessment(scores)
        assert len(result["dealbreakers"]) > 0
        assert "🚫" in result["verdict"]

    def test_dealbreaker_outside_circle(self):
        scores = {
            "profitability": 4, "health": 4, "cashflow": 4,
            "valuation": 4, "growth": 4, "dividend": 3,
            "ownership": 4, "strategy": 4,
        }
        result = integrated_assessment(
            scores,
            qualitative={"circle_of_competence": False},
        )
        assert "能力圈" in result["dealbreakers"][0]

    def test_format_output(self):
        scores = {
            "profitability": 4, "health": 3, "cashflow": 3,
            "valuation": 3, "growth": 3, "dividend": 3,
            "ownership": 3, "strategy": 3,
        }
        result = integrated_assessment(scores)
        output = format_integrated_assessment(result)
        assert "综合投资框架评估" in output
        assert "林奇分类" in output
        assert "Pre-mortem" in output
        assert "综合结论" in output
