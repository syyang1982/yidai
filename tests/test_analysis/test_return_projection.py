"""回报预测模块测试。"""
import pytest

from src.analysis.return_projection import project_returns, format_projection


def _buy_data(**overrides):
    base = {
        "current_price": 50.0,
        "pe_ratio": 14,
        "pe_history_percentile": 0.25,
        "revenue_growth": 0.25,
        "net_margin": 0.12,
        "roe": 0.18,
        "dividend_yield": 0.02,
        "signal": "BUY",
    }
    base.update(overrides)
    return base


def _reduce_data(**overrides):
    base = {
        "current_price": 100.0,
        "pe_ratio": 45,
        "pe_history_percentile": 0.85,
        "revenue_growth": 0.10,
        "net_margin": 0.08,
        "roe": 0.12,
        "dividend_yield": 0.01,
        "signal": "REDUCE",
    }
    base.update(overrides)
    return base


def _hold_data(**overrides):
    base = {
        "current_price": 30.0,
        "pe_ratio": 22,
        "pe_history_percentile": 0.50,
        "revenue_growth": 0.05,
        "net_margin": 0.10,
        "roe": 0.12,
        "dividend_yield": 0.03,
        "signal": "HOLD",
    }
    base.update(overrides)
    return base


class TestBuySignal:
    def test_positive_central_estimate(self):
        r = project_returns(_buy_data())
        assert r["expected_12m_return"] > 0

    def test_bull_central_bear_order(self):
        r = project_returns(_buy_data())
        assert r["bull_case"] > r["expected_12m_return"]
        assert r["expected_12m_return"] > r["bear_case"]

    def test_has_all_fields(self):
        r = project_returns(_buy_data())
        for key in ("expected_12m_return", "bull_case", "bear_case",
                     "return_range", "key_drivers", "key_risks",
                     "confidence", "reasoning"):
            assert key in r


class TestReduceSignal:
    def test_negative_central_estimate(self):
        r = project_returns(_reduce_data())
        assert r["expected_12m_return"] < 0

    def test_bear_worse_than_central(self):
        r = project_returns(_reduce_data())
        assert r["bear_case"] < r["expected_12m_return"]

    def test_bull_is_mild_decline(self):
        r = project_returns(_reduce_data())
        assert r["bull_case"] == pytest.approx(-0.05)


class TestHoldSignal:
    def test_modest_return(self):
        r = project_returns(_hold_data())
        # Should be roughly earnings_yield + dividend ≈ 4.5% + 3% ≈ 7.5%
        assert 0.02 < r["expected_12m_return"] < 0.15

    def test_tighter_range(self):
        r = project_returns(_hold_data())
        spread = r["bull_case"] - r["bear_case"]
        # HOLD range should be tighter than BUY
        buy_r = project_returns(_buy_data())
        buy_spread = buy_r["bull_case"] - buy_r["bear_case"]
        assert spread < buy_spread


class TestLowPEHighGrowth:
    def test_high_confidence(self):
        r = project_returns(_buy_data(pe_ratio=10, revenue_growth=0.30, roe=0.20))
        assert r["confidence"] == 5

    def test_favorable_range(self):
        r = project_returns(_buy_data(pe_ratio=10, revenue_growth=0.30, roe=0.20))
        assert r["expected_12m_return"] > 0.15


class TestHighPELowGrowth:
    def test_low_confidence(self):
        r = project_returns(_buy_data(pe_ratio=50, revenue_growth=0.02, roe=0.05))
        assert r["confidence"] <= 2

    def test_high_valuation_risk(self):
        r = project_returns(_buy_data(pe_ratio=50, revenue_growth=0.02))
        assert any("高估值" in risk for risk in r["key_risks"])


class TestDividendContribution:
    def test_dividend_adds_to_return(self):
        r_no_div = project_returns(_buy_data(dividend_yield=0))
        r_div = project_returns(_buy_data(dividend_yield=0.05))
        assert r_div["expected_12m_return"] > r_no_div["expected_12m_return"]

    def test_high_dividend_driver(self):
        r = project_returns(_buy_data(dividend_yield=0.05))
        assert any("股息" in d for d in r["key_drivers"])


class TestPEReversion:
    def test_low_pe_positive_reversion(self):
        r_low = project_returns(_buy_data(pe_history_percentile=0.10))
        r_mid = project_returns(_buy_data(pe_history_percentile=0.50))
        assert r_low["expected_12m_return"] > r_mid["expected_12m_return"]

    def test_high_pe_negative_reversion(self):
        r_high = project_returns(_buy_data(pe_history_percentile=0.90))
        r_mid = project_returns(_buy_data(pe_history_percentile=0.50))
        assert r_high["expected_12m_return"] < r_mid["expected_12m_return"]


class TestFormatProjection:
    def test_contains_emoji_and_chinese(self):
        proj = project_returns(_buy_data())
        text = format_projection(proj, "BUY")
        assert "📊" in text
        assert "回报预期" in text
        assert "置信度" in text

    def test_contains_stars(self):
        proj = project_returns(_buy_data())
        text = format_projection(proj, "BUY")
        assert "★" in text

    def test_contains_percentages(self):
        proj = project_returns(_buy_data())
        text = format_projection(proj, "BUY")
        assert "%" in text


class TestEdgeCases:
    def test_pe_zero(self):
        r = project_returns(_buy_data(pe_ratio=0))
        assert r["expected_12m_return"] is not None
        assert r["bear_case"] is not None

    def test_negative_growth(self):
        r = project_returns(_buy_data(revenue_growth=-0.10))
        assert r["expected_12m_return"] is not None
        assert any("收入下滑" in risk for risk in r["key_risks"])

    def test_missing_fields(self):
        r = project_returns({"signal": "BUY"})
        assert r["expected_12m_return"] is not None
        assert r["confidence"] in range(1, 6)

    def test_none_values(self):
        r = project_returns({
            "pe_ratio": None,
            "revenue_growth": None,
            "dividend_yield": None,
            "signal": "HOLD",
        })
        assert r["expected_12m_return"] is not None
