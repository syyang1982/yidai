"""
Tests for the terminal visualization dashboard.

Tests:
- render_portfolio_dashboard with mock data
- render_score_radar with various score combinations
- Edge cases: empty portfolio, missing data
"""

import pytest
import sys
import os

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.viz.dashboard import (
    render_portfolio_dashboard,
    render_score_radar,
    _display_width,
    _pad,
    _extract_risks,
)


# ── CJK Width Tests ───────────────────────────────────────────────────────

class TestDisplayWidth:
    def test_ascii_chars(self):
        assert _display_width("hello") == 5

    def test_cjk_chars(self):
        assert _display_width("意怠工程") == 8

    def test_mixed_chars(self):
        assert _display_width("hi意怠") == 6  # 2 + 4

    def test_empty_string(self):
        assert _display_width("") == 0

    def test_numbers(self):
        assert _display_width("12345") == 5


class TestPad:
    def test_pad_left(self):
        result = _pad("abc", 6, "left")
        assert result == "abc   "
        assert _display_width(result) == 6

    def test_pad_right(self):
        result = _pad("abc", 6, "right")
        assert result == "   abc"
        assert _display_width(result) == 6

    def test_pad_center(self):
        result = _pad("abc", 7, "center")
        assert _display_width(result) == 7

    def test_pad_cjk(self):
        result = _pad("意怠", 8, "left")
        assert _display_width(result) == 8

    def test_pad_no_pad_needed(self):
        result = _pad("abcdef", 4, "left")
        assert result == "abcdef"


# ── Portfolio Dashboard Tests ─────────────────────────────────────────────

def _make_mock_portfolio():
    """Create mock portfolio data for testing."""
    return {
        "holdings": [
            {
                "ticker": "1810.HK",
                "name": "Xiaomi",
                "shares": 36000,
                "avg_cost": 30.87,
                "price_ccy": "HKD",
            },
            {
                "ticker": "LX",
                "name": "LexinFintech",
                "shares": 2250,
                "avg_cost": 5.454,
                "price_ccy": "USD",
            },
            {
                "ticker": "9999.HK",
                "name": "NetEase",
                "shares": 200,
                "avg_cost": 187.83,
                "price_ccy": "HKD",
            },
        ],
        "prices": {
            "1810.HK": {"price": 28.38, "currency": "HKD"},
            "LX": {"price": 2.19, "currency": "USD"},
            "9999.HK": {"price": 192.9, "currency": "HKD"},
        },
        "exchange_rates": {
            "CNY_PER_HKD": 0.87,
            "USD_PER_HKD": 0.128,
        },
    }


def _make_mock_scores():
    """Create mock scores data for testing."""
    return {
        "1810.HK": {
            "total_score": 25,
            "grade": "B",
            "signal": "HOLD",
            "price": 28.38,
            "scores": {
                "profitability": 4, "health": 4, "cashflow": 3,
                "valuation": 3, "growth": 4, "ownership": 4, "strategy": 3,
            },
        },
        "LX": {
            "total_score": 18,
            "grade": "C",
            "signal": "WATCH",
            "price": 2.19,
            "scores": {
                "profitability": 3, "health": 3, "cashflow": 2,
                "valuation": 4, "growth": 2, "ownership": 2, "strategy": 2,
            },
        },
        "9999.HK": {
            "total_score": 30,
            "grade": "A",
            "signal": "BUY",
            "price": 192.9,
            "scores": {
                "profitability": 5, "health": 4, "cashflow": 4,
                "valuation": 5, "growth": 4, "ownership": 4, "strategy": 4,
            },
        },
    }


class TestRenderPortfolioDashboard:
    def test_basic_output(self):
        """Dashboard renders without errors with mock data."""
        portfolio = _make_mock_portfolio()
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_portfolio_summary(self):
        """Dashboard contains summary section."""
        portfolio = _make_mock_portfolio()
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert "组合总览" in result
        assert "总市值" in result
        assert "持仓数" in result

    def test_contains_position_table(self):
        """Dashboard contains position table."""
        portfolio = _make_mock_portfolio()
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert "持仓明细" in result
        assert "1810.HK" in result
        assert "LX" in result
        assert "9999.HK" in result

    def test_contains_signal_distribution(self):
        """Dashboard contains signal distribution."""
        portfolio = _make_mock_portfolio()
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert "信号分布" in result
        assert "买入" in result
        assert "持有" in result
        assert "观望" in result

    def test_contains_risk_section(self):
        """Dashboard contains risk section."""
        portfolio = _make_mock_portfolio()
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert "风险提示" in result

    def test_contains_grades(self):
        """Dashboard shows grades."""
        portfolio = _make_mock_portfolio()
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert "B" in result
        assert "C" in result
        assert "A" in result

    def test_with_anomaly_alerts(self):
        """Dashboard displays anomaly alerts as risks."""
        portfolio = _make_mock_portfolio()
        portfolio["anomaly_alerts"] = [
            "Xiaomi PE过高，估值泡沫风险",
            "LX现金流紧张",
        ]
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert "Xiaomi PE过高" in result
        assert "LX现金流紧张" in result

    def test_box_characters(self):
        """Dashboard uses proper box-drawing characters."""
        portfolio = _make_mock_portfolio()
        scores = _make_mock_scores()
        result = render_portfolio_dashboard(portfolio, scores)

        assert "╔" in result
        assert "╚" in result
        assert "║" in result

    def test_cjk_alignment(self):
        """Dashboard handles CJK characters in display without errors."""
        portfolio = {
            "holdings": [
                {
                    "ticker": "1810.HK",
                    "name": "小米集团",  # CJK name
                    "shares": 36000,
                    "avg_cost": 30.87,
                    "price_ccy": "HKD",
                },
            ],
            "prices": {"1810.HK": {"price": 28.38, "currency": "HKD"}},
            "exchange_rates": {"CNY_PER_HKD": 0.87, "USD_PER_HKD": 0.128},
        }
        scores = {
            "1810.HK": {
                "total_score": 25,
                "grade": "B",
                "signal": "HOLD",
                "price": 28.38,
                "scores": {},
            },
        }
        result = render_portfolio_dashboard(portfolio, scores)

        # Should render without errors
        assert "小米集团" in result
        assert len(result) > 0


# ── Empty Portfolio Edge Cases ─────────────────────────────────────────────

class TestEmptyPortfolio:
    def test_empty_holdings(self):
        """Dashboard handles empty holdings gracefully."""
        portfolio = {"holdings": [], "prices": {}, "exchange_rates": {}}
        scores = {}
        result = render_portfolio_dashboard(portfolio, scores)

        assert "暂无持仓数据" in result

    def test_missing_prices(self):
        """Dashboard handles missing price data."""
        portfolio = {
            "holdings": [
                {
                    "ticker": "TEST.HK",
                    "name": "TestCo",
                    "shares": 100,
                    "avg_cost": 10.0,
                    "price_ccy": "HKD",
                },
            ],
            "prices": {},  # No prices
            "exchange_rates": {},
        }
        scores = {}
        result = render_portfolio_dashboard(portfolio, scores)

        # Should render without errors, show N/A for price
        assert "TEST.HK" in result
        assert "N/A" in result

    def test_missing_exchange_rates(self):
        """Dashboard handles missing exchange rates."""
        portfolio = {
            "holdings": [
                {
                    "ticker": "LX",
                    "name": "LexinFintech",
                    "shares": 100,
                    "avg_cost": 5.0,
                    "price_ccy": "USD",
                },
            ],
            "prices": {"LX": {"price": 2.0, "currency": "USD"}},
            "exchange_rates": {},  # Missing rates
        }
        scores = {}
        # Should not crash - falls back to defaults
        result = render_portfolio_dashboard(portfolio, scores)
        assert "LX" in result

    def test_missing_scores(self):
        """Dashboard handles missing scores gracefully."""
        portfolio = _make_mock_portfolio()
        scores = {}  # No scores
        result = render_portfolio_dashboard(portfolio, scores)

        # Should still render positions
        assert "1810.HK" in result

    def test_partial_scores(self):
        """Dashboard handles partial scores."""
        portfolio = _make_mock_portfolio()
        scores = {
            "1810.HK": {
                "total_score": 25,
                "grade": "B",
                "signal": "HOLD",
                "price": 28.38,
            },
            # LX and 9999.HK missing
        }
        result = render_portfolio_dashboard(portfolio, scores)
        assert "1810.HK" in result
        assert "LX" in result


# ── Radar Chart Tests ─────────────────────────────────────────────────────

def _make_full_scores():
    """Create a full 7-dimension score dict."""
    return {
        "profitability": 4,
        "health": 3,
        "cashflow": 4,
        "valuation": 5,
        "growth": 3,
        "ownership": 4,
        "strategy": 3,
    }


class TestRenderScoreRadar:
    def test_basic_output(self):
        """Radar chart renders without errors."""
        scores = _make_full_scores()
        result = render_score_radar(scores)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_dimensions(self):
        """Radar chart contains all dimension labels."""
        scores = _make_full_scores()
        result = render_score_radar(scores)

        assert "盈利" in result
        assert "健康" in result
        assert "现金流" in result
        assert "估值" in result
        assert "成长" in result
        assert "股东" in result
        assert "战略" in result

    def test_contains_total_and_grade(self):
        """Radar chart shows total score and grade."""
        scores = _make_full_scores()
        result = render_score_radar(scores)

        assert "总分" in result
        assert "26/40" in result  # 4+3+4+5+3+4+3 = 26
        assert "B" in result      # 26 is in B range (22-28)

    def test_all_zeros(self):
        """Radar chart handles all-zero scores."""
        scores = {k: 0 for k in [
            "profitability", "health", "cashflow",
            "valuation", "growth", "dividend", "ownership", "strategy",
        ]}
        result = render_score_radar(scores)

        assert "0/40" in result
        assert "F" in result

    def test_all_fives(self):
        """Radar chart handles perfect scores."""
        scores = {k: 5 for k in [
            "profitability", "health", "cashflow",
            "valuation", "growth", "dividend", "ownership", "strategy",
        ]}
        result = render_score_radar(scores)

        assert "40/40" in result
        assert "A" in result

    def test_empty_scores(self):
        """Radar chart handles empty/missing scores."""
        scores = {}
        result = render_score_radar(scores)

        assert "0/40" in result
        assert "F" in result

    def test_partial_scores(self):
        """Radar chart handles partial dimension scores."""
        scores = {"profitability": 4, "health": 3}
        result = render_score_radar(scores)

        assert "盈利" in result
        assert "7/40" in result  # 4+3+0+0+0+0+0+0 = 7

    def test_none_values(self):
        """Radar chart handles None values gracefully."""
        scores = {
            "profitability": 4,
            "health": None,
            "cashflow": 3,
            "valuation": None,
            "growth": 2,
            "dividend": None,
            "ownership": 1,
            "strategy": None,
        }
        result = render_score_radar(scores)

        # None values should be treated as 0
        assert "10/40" in result  # 4+0+3+0+2+0+1+0 = 10

    def test_grade_thresholds(self):
        """Radar chart shows correct grades for different totals."""
        # A grade: 33+
        scores_a = {k: 5 for k in [
            "profitability", "health", "cashflow",
            "valuation", "growth", "dividend", "ownership", "strategy",
        ]}
        assert "A" in render_score_radar(scores_a)

        # C grade: 17-25
        scores_c = {
            "profitability": 3, "health": 2, "cashflow": 2,
            "valuation": 2, "growth": 2, "dividend": 2, "ownership": 2, "strategy": 2,
        }
        result_c = render_score_radar(scores_c)
        assert "17/40" in result_c
        assert "C" in result_c

    def test_score_clamping(self):
        """Radar chart clamps scores to 0-5 range."""
        scores = {
            "profitability": 10,  # Over max
            "health": -5,         # Under min
            "cashflow": 3,
            "valuation": 3,
            "growth": 3,
            "dividend": 3,
            "ownership": 3,
            "strategy": 3,
        }
        result = render_score_radar(scores)

        # Should clamp: 5+0+3+3+3+3+3 = 20
        assert "23/40" in result

    def test_box_characters(self):
        """Radar chart uses box-drawing characters."""
        scores = _make_full_scores()
        result = render_score_radar(scores)

        assert "╔" in result
        assert "╚" in result
        assert "║" in result

    def test_contains_bar_chars(self):
        """Radar chart contains bar visualization characters."""
        scores = _make_full_scores()
        result = render_score_radar(scores)

        assert "█" in result
        assert "░" in result


# ── Risk Extraction Tests ─────────────────────────────────────────────────

class TestExtractRisks:
    def test_from_anomaly_alerts(self):
        """Risks extracted from anomaly alerts."""
        positions = []
        alerts = ["风险1", "风险2", "风险3"]
        risks = _extract_risks(positions, alerts)
        assert len(risks) == 3
        assert risks[0] == "风险1"

    def test_from_losing_positions(self):
        """Risks extracted from losing positions."""
        positions = [
            {"name": "A", "ticker": "A", "pnl_pct": -20.0, "weight": 10},
            {"name": "B", "ticker": "B", "pnl_pct": -15.0, "weight": 10},
            {"name": "C", "ticker": "C", "pnl_pct": 5.0, "weight": 10},
        ]
        risks = _extract_risks(positions, [])
        assert any("A" in r for r in risks)

    def test_concentrated_positions(self):
        """Risks include concentrated positions."""
        positions = [
            {"name": "Big", "ticker": "BIG", "pnl_pct": 5.0, "weight": 35},
            {"name": "Small", "ticker": "SM", "pnl_pct": 2.0, "weight": 5},
        ]
        risks = _extract_risks(positions, [])
        assert any("35" in r or "集中" in r for r in risks)

    def test_no_risks(self):
        """Default risk when nothing notable."""
        positions = [
            {"name": "OK", "ticker": "OK", "pnl_pct": 5.0, "weight": 10},
        ]
        risks = _extract_risks(positions, [])
        assert len(risks) >= 1

    def test_max_three_risks(self):
        """At most 3 risks returned."""
        positions = []
        alerts = ["r1", "r2", "r3", "r4", "r5"]
        risks = _extract_risks(positions, alerts)
        assert len(risks) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
