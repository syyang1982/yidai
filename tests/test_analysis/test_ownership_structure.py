"""Tests for the ownership structure analysis module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.ownership_structure import (
    analyze_controller_status,
    format_ownership_structure,
)


# ---------------------------------------------------------------------------
# analyze_controller_status — no data
# ---------------------------------------------------------------------------

class TestNoData:
    def test_empty_shareholders(self):
        result = analyze_controller_status([])
        assert result["has_controller"] is False
        assert result["category"] == "unknown"
        assert "无十大股东数据" in result["warnings"][0]

    def test_none_shareholders(self):
        result = analyze_controller_status(None)
        assert result["category"] == "unknown"


# ---------------------------------------------------------------------------
# analyze_controller_status — closely held (>60%)
# ---------------------------------------------------------------------------

class TestCloselyHeld:
    def test_single_majority_holder(self):
        shareholders = [
            {"name": "控股股东A", "pct": 65.0, "type": "legal_entity"},
            {"name": "基金B", "pct": 5.0, "type": "fund"},
            {"name": "个人C", "pct": 3.0, "type": "natural_person"},
        ]
        result = analyze_controller_status(shareholders)
        assert result["has_controller"] is True
        assert result["category"] == "closely_held"
        assert result["controller_name"] == "控股股东A"
        assert result["controller_pct"] == 65.0
        assert "收购可能性极低" in result["opportunity"]
        assert len(result["warnings"]) >= 1

    def test_state_owned_majority(self):
        shareholders = [
            {"name": "国资委", "pct": 70.0, "type": "state"},
            {"name": "社保基金", "pct": 5.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        assert result["category"] == "closely_held"
        assert result["controller_name"] == "国资委"


# ---------------------------------------------------------------------------
# analyze_controller_status — has controller (30-60%)
# ---------------------------------------------------------------------------

class TestHasController:
    def test_clear_controller(self):
        shareholders = [
            {"name": "创始人张某", "pct": 45.0, "type": "natural_person"},
            {"name": "投资机构A", "pct": 8.0, "type": "fund"},
            {"name": "投资机构B", "pct": 5.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        assert result["has_controller"] is True
        assert result["category"] == "has_controller"
        assert result["controller_name"] == "创始人张某"
        assert "控制权稳固" in result["warnings"][0] or "收购可能性较低" in result["opportunity"]

    def test_controller_with_close_second(self):
        """When second holder is close to first, flag potential power struggle."""
        shareholders = [
            {"name": "大股东A", "pct": 35.0, "type": "legal_entity"},
            {"name": "大股东B", "pct": 28.0, "type": "legal_entity"},
            {"name": "基金C", "pct": 5.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        assert result["has_controller"] is True
        assert result["category"] == "has_controller"
        # Should warn about potential power struggle
        assert any("争夺" in w or "差距" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# analyze_controller_status — no controller (20-30%)
# ---------------------------------------------------------------------------

class TestNoController:
    def test_no_clear_controller(self):
        shareholders = [
            {"name": "股东A", "pct": 25.0, "type": "legal_entity"},
            {"name": "股东B", "pct": 18.0, "type": "legal_entity"},
            {"name": "股东C", "pct": 12.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        assert result["has_controller"] is False
        assert result["category"] == "no_controller"
        assert "收购" in result["opportunity"] or "举牌" in result["opportunity"]
        assert any("无实际控制人" in w for w in result["warnings"])

    def test_no_controller_with_second_holder_info(self):
        """When second holder is >10%, should mention multi-party dynamics."""
        shareholders = [
            {"name": "股东A", "pct": 22.0, "type": "legal_entity"},
            {"name": "股东B", "pct": 15.0, "type": "legal_entity"},
            {"name": "基金C", "pct": 8.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        assert result["category"] == "no_controller"
        assert any("博弈" in w or "第二" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# analyze_controller_status — dispersed (<20%)
# ---------------------------------------------------------------------------

class TestDispersed:
    def test_highly_dispersed(self):
        shareholders = [
            {"name": "基金A", "pct": 12.0, "type": "fund"},
            {"name": "基金B", "pct": 8.0, "type": "fund"},
            {"name": "基金C", "pct": 5.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        assert result["has_controller"] is False
        assert result["category"] == "dispersed"
        all_warnings = " ".join(result["warnings"])
        assert "野蛮人" in all_warnings or "举牌" in all_warnings
        assert any("散户" in w for w in result["warnings"])

    def test_dispersed_opportunity_message(self):
        shareholders = [
            {"name": "基金A", "pct": 15.0, "type": "fund"},
            {"name": "基金B", "pct": 10.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        assert "优质收购标的" in result["opportunity"]


# ---------------------------------------------------------------------------
# Acting-in-concert groups
# ---------------------------------------------------------------------------

class TestActingInConcert:
    def test_concert_group_creates_effective_controller(self):
        """Individual shareholders with acting_in_concert should be grouped."""
        shareholders = [
            {"name": "创始人A", "pct": 18.0, "type": "natural_person",
             "acting_in_concert": ["创始人A", "创始人B"]},
            {"name": "创始人B", "pct": 15.0, "type": "natural_person",
             "acting_in_concert": ["创始人A", "创始人B"]},
            {"name": "基金C", "pct": 10.0, "type": "fund"},
            {"name": "基金D", "pct": 8.0, "type": "fund"},
        ]
        result = analyze_controller_status(shareholders)
        # Combined: 18+15 = 33% => has_controller
        assert result["has_controller"] is True
        assert result["category"] == "has_controller"
        assert result["controller_pct"] == 33.0


# ---------------------------------------------------------------------------
# Top shareholders extraction
# ---------------------------------------------------------------------------

class TestTopShareholders:
    def test_top3_extracted_correctly(self):
        shareholders = [
            {"name": "A", "pct": 30.0},
            {"name": "B", "pct": 20.0},
            {"name": "C", "pct": 10.0},
            {"name": "D", "pct": 5.0},
        ]
        result = analyze_controller_status(shareholders)
        top = result["top_shareholders"]
        assert len(top) == 3
        assert top[0] == ("A", 30.0)
        assert top[1] == ("B", 20.0)
        assert top[2] == ("C", 10.0)

    def test_unsorted_input_sorted_by_pct(self):
        shareholders = [
            {"name": "C", "pct": 10.0},
            {"name": "A", "pct": 30.0},
            {"name": "B", "pct": 20.0},
        ]
        result = analyze_controller_status(shareholders)
        assert result["top_shareholders"][0] == ("A", 30.0)


# ---------------------------------------------------------------------------
# format_ownership_structure
# ---------------------------------------------------------------------------

class TestFormatOwnership:
    def test_unknown_returns_empty(self):
        result = {"category": "unknown", "opportunity": "", "warnings": []}
        assert format_ownership_structure(result) == ""

    def test_closely_held_format(self):
        result = {
            "category": "closely_held",
            "opportunity": "股权高度集中，收购可能性极低",
            "controller_name": "国资委",
            "controller_pct": 70.0,
            "top_shareholders": [("国资委", 70.0), ("社保基金", 5.0)],
            "warnings": ["ℹ️ 国资委持股70.0%，股权高度集中"],
        }
        output = format_ownership_structure(result)
        assert "🔒" in output
        assert "国资委" in output
        assert "70.0%" in output

    def test_no_controller_format(self):
        result = {
            "category": "no_controller",
            "opportunity": "无实际控制人 — 存在收购/举牌可能",
            "controller_name": None,
            "controller_pct": 25.0,
            "top_shareholders": [("股东A", 25.0), ("股东B", 18.0)],
            "warnings": ["🔔 无实际控制人: 最大股东股东A仅持25.0%"],
        }
        output = format_ownership_structure(result)
        assert "🔔" in output
        assert "无实际控制人" in output

    def test_dispersed_format(self):
        result = {
            "category": "dispersed",
            "opportunity": "股权高度分散 — 优质收购标的",
            "controller_name": None,
            "controller_pct": 12.0,
            "top_shareholders": [("基金A", 12.0)],
            "warnings": ["🔥 股权高度分散"],
        }
        output = format_ownership_structure(result)
        assert "🔥" in output


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_shareholder(self):
        shareholders = [{"name": "唯一股东", "pct": 100.0, "type": "legal_entity"}]
        result = analyze_controller_status(shareholders)
        assert result["has_controller"] is True
        assert result["category"] == "closely_held"
        assert result["controller_pct"] == 100.0

    def test_zero_pct_shareholder(self):
        """Shareholders with 0% should not affect analysis."""
        shareholders = [
            {"name": "大股东", "pct": 25.0},
            {"name": "零持股", "pct": 0.0},
        ]
        result = analyze_controller_status(shareholders)
        assert result["category"] == "no_controller"
        assert result["controller_pct"] == 25.0

    def test_effective_pcts_returned(self):
        shareholders = [
            {"name": "A", "pct": 15.0},
            {"name": "B", "pct": 10.0},
            {"name": "C", "pct": 8.0},
        ]
        result = analyze_controller_status(shareholders)
        effective = result.get("effective_pcts", {})
        assert "A" in effective
        assert effective["A"] == 15.0

    def test_boundary_at_30_pct(self):
        """Exactly 30% should classify as has_controller (the threshold is >30)."""
        shareholders = [{"name": "A", "pct": 30.0}]
        result = analyze_controller_status(shareholders)
        # 30% is NOT > 30, so it falls into no_controller
        assert result["category"] == "no_controller"

    def test_boundary_at_31_pct(self):
        shareholders = [{"name": "A", "pct": 31.0}]
        result = analyze_controller_status(shareholders)
        assert result["category"] == "has_controller"
