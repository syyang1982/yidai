"""Tests for src/analysis/anomaly.py — 财务异常检测。"""

import pytest

from src.analysis.anomaly import (
    AnomalyAlert,
    detect_anomalies,
    format_alerts,
    _check_ar_vs_revenue,
    _check_inventory_turnover,
    _check_profit_quality,
    _check_short_loan_long_invest,
    _check_goodwill_ratio,
)


def _make_annual(records: list[dict]) -> list[dict]:
    """Helper: build annual data list from partial dicts, filling period."""
    result = []
    for i, r in enumerate(records):
        d = {"period": f"202{i+1}-12-31", "ticker": "TEST"}
        d.update(r)
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# W1.1.1: 应收账款 vs 营收增速
# ---------------------------------------------------------------------------
class TestARvsRevenue:
    def test_no_alert_normal(self):
        data = _make_annual([
            {"revenue": 100, "accounts_receivable": 20},
            {"revenue": 120, "accounts_receivable": 22},  # AR +10%, Rev +20%
        ])
        alerts = _check_ar_vs_revenue("TEST", data, "测试公司")
        assert len(alerts) == 0

    def test_one_period_medium(self):
        data = _make_annual([
            {"revenue": 100, "accounts_receivable": 20},
            {"revenue": 110, "accounts_receivable": 40},  # AR +100%, Rev +10% → gap=90%
        ])
        alerts = _check_ar_vs_revenue("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert alerts[0].severity == "MEDIUM"
        assert alerts[0].rule_id == "W1.1.1"

    def test_consecutive_two_high(self):
        data = _make_annual([
            {"revenue": 100, "accounts_receivable": 20},
            {"revenue": 110, "accounts_receivable": 40},   # gap > 10%
            {"revenue": 120, "accounts_receivable": 70},   # gap > 10%
        ])
        alerts = _check_ar_vs_revenue("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert alerts[0].severity == "HIGH"
        assert "连续" in alerts[0].detail

    def test_gap_resets_count(self):
        data = _make_annual([
            {"revenue": 100, "accounts_receivable": 20},
            {"revenue": 110, "accounts_receivable": 40},   # gap
            {"revenue": 150, "accounts_receivable": 45},   # no gap (reset)
            {"revenue": 160, "accounts_receivable": 80},   # gap again, but only 1
        ])
        alerts = _check_ar_vs_revenue("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert alerts[0].severity == "MEDIUM"  # only 1 consecutive

    def test_missing_data_skipped(self):
        data = _make_annual([
            {"revenue": 100, "accounts_receivable": None},
            {"revenue": 110, "accounts_receivable": 40},
        ])
        alerts = _check_ar_vs_revenue("TEST", data, "测试公司")
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# W1.1.2: 存货周转率趋势
# ---------------------------------------------------------------------------
class TestInventoryTurnover:
    def test_no_alert_rising(self):
        data = _make_annual([
            {"revenue": 100, "inventory": 50},
            {"revenue": 120, "inventory": 40},
            {"revenue": 150, "inventory": 30},
            {"revenue": 180, "inventory": 25},
        ])
        alerts = _check_inventory_turnover("TEST", data, "测试公司")
        assert len(alerts) == 0

    def test_three_declining(self):
        data = _make_annual([
            {"revenue": 100, "inventory": 20},  # turnover=5.0
            {"revenue": 100, "inventory": 25},  # turnover=4.0
            {"revenue": 100, "inventory": 33},  # turnover=3.0
            {"revenue": 100, "inventory": 50},  # turnover=2.0
        ])
        alerts = _check_inventory_turnover("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert alerts[0].severity == "MEDIUM"
        assert alerts[0].rule_id == "W1.1.2"

    def test_two_declining_not_enough(self):
        data = _make_annual([
            {"revenue": 100, "inventory": 20},
            {"revenue": 100, "inventory": 25},
            {"revenue": 100, "inventory": 30},
        ])
        alerts = _check_inventory_turnover("TEST", data, "测试公司")
        assert len(alerts) == 0  # only 2 declining, need 3

    def test_missing_inventory(self):
        data = _make_annual([
            {"revenue": 100, "inventory": None},
            {"revenue": 100, "inventory": None},
            {"revenue": 100, "inventory": None},
            {"revenue": 100, "inventory": None},
        ])
        alerts = _check_inventory_turnover("TEST", data, "测试公司")
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# W1.1.3: 利润质量
# ---------------------------------------------------------------------------
class TestProfitQuality:
    def test_no_alert_ocf_higher(self):
        data = _make_annual([
            {"net_income": 100, "operating_cash_flow": 120},
            {"net_income": 110, "operating_cash_flow": 130},
        ])
        alerts = _check_profit_quality("TEST", data, "测试公司")
        assert len(alerts) == 0

    def test_two_periods_low(self):
        data = _make_annual([
            {"net_income": 100, "operating_cash_flow": 120},
            {"net_income": 100, "operating_cash_flow": 60},  # OCF < NI
            {"net_income": 110, "operating_cash_flow": 70},  # OCF < NI
        ])
        alerts = _check_profit_quality("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert alerts[0].severity == "MEDIUM"
        assert alerts[0].rule_id == "W1.1.3"

    def test_loss_company_skipped(self):
        data = _make_annual([
            {"net_income": -50, "operating_cash_flow": 30},
            {"net_income": -30, "operating_cash_flow": 20},
        ])
        alerts = _check_profit_quality("TEST", data, "测试公司")
        assert len(alerts) == 0  # loss-making companies excluded

    def test_mixed_breaks_streak(self):
        data = _make_annual([
            {"net_income": 100, "operating_cash_flow": 60},
            {"net_income": 100, "operating_cash_flow": 120},  # breaks streak
            {"net_income": 100, "operating_cash_flow": 60},
        ])
        alerts = _check_profit_quality("TEST", data, "测试公司")
        assert len(alerts) == 0  # no 2 consecutive


# ---------------------------------------------------------------------------
# W1.1.4: 短贷长投
# ---------------------------------------------------------------------------
class TestShortLoanLongInvest:
    def test_no_alert_normal(self):
        data = _make_annual([
            {"short_loan": 100, "long_term_invest": 50, "total_assets": 1000},
            {"short_loan": 110, "long_term_invest": 55, "total_assets": 1100},
        ])
        alerts = _check_short_loan_long_invest("TEST", data, "测试公司")
        assert len(alerts) == 0

    def test_alert_triggered(self):
        data = _make_annual([
            {"short_loan": 100, "long_term_invest": 50, "total_assets": 1000},
            # short_loan: +50% (100→150), ratio=150/1200=12.5%>5%, lti: +40%
            {"short_loan": 150, "long_term_invest": 70, "total_assets": 1200},
        ])
        alerts = _check_short_loan_long_invest("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert alerts[0].severity == "HIGH"
        assert alerts[0].rule_id == "W1.1.4"

    def test_short_loan_up_but_lti_down(self):
        data = _make_annual([
            {"short_loan": 100, "long_term_invest": 50, "total_assets": 1000},
            {"short_loan": 150, "long_term_invest": 40, "total_assets": 1200},
        ])
        alerts = _check_short_loan_long_invest("TEST", data, "测试公司")
        assert len(alerts) == 0  # LTI didn't increase

    def test_short_loan_ratio_too_low(self):
        data = _make_annual([
            {"short_loan": 10, "long_term_invest": 50, "total_assets": 1000},
            {"short_loan": 15, "long_term_invest": 70, "total_assets": 1000},
        ])
        alerts = _check_short_loan_long_invest("TEST", data, "测试公司")
        assert len(alerts) == 0  # ratio = 1.5% < 5%


# ---------------------------------------------------------------------------
# W1.1.5: 商誉占比
# ---------------------------------------------------------------------------
class TestGoodwillRatio:
    def test_no_alert_low_goodwill(self):
        data = _make_annual([
            {"goodwill": 50, "total_assets": 1000},
            {"goodwill": 60, "total_assets": 1100},
        ])
        alerts = _check_goodwill_ratio("TEST", data, "测试公司")
        assert len(alerts) == 0

    def test_high_and_rising(self):
        data = _make_annual([
            {"goodwill": 50, "total_assets": 1000},   # 5%
            {"goodwill": 200, "total_assets": 1000},   # 20%, delta=15%
        ])
        alerts = _check_goodwill_ratio("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert alerts[0].severity == "MEDIUM"
        assert "上升" in alerts[0].detail

    def test_high_stable(self):
        data = _make_annual([
            {"goodwill": 250, "total_assets": 1000},  # 25%
            {"goodwill": 260, "total_assets": 1000},  # 26%, delta=1% < 5%
        ])
        alerts = _check_goodwill_ratio("TEST", data, "测试公司")
        assert len(alerts) == 1
        assert "过高" in alerts[0].detail

    def test_missing_data(self):
        data = _make_annual([
            {"goodwill": None, "total_assets": 1000},
            {"goodwill": None, "total_assets": 1000},
        ])
        alerts = _check_goodwill_ratio("TEST", data, "测试公司")
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# detect_anomalies (integration)
# ---------------------------------------------------------------------------
class TestDetectAnomalies:
    def test_no_data_returns_empty(self):
        alerts = detect_anomalies("TEST", [], "测试公司")
        assert alerts == []

    def test_single_period_returns_empty(self):
        data = _make_annual([{"revenue": 100}])
        alerts = detect_anomalies("TEST", data, "测试公司")
        assert alerts == []

    def test_multiple_alerts_sorted_by_severity(self):
        """Trigger multiple rules and verify HIGH comes before MEDIUM."""
        data = _make_annual([
            {
                "revenue": 1000, "accounts_receivable": 100,
                "inventory": 50, "net_income": 200, "operating_cash_flow": 250,
                "short_loan": 50, "long_term_invest": 30, "total_assets": 2000,
                "goodwill": 100,
            },
            {
                "revenue": 1100, "accounts_receivable": 300,  # AR gap >> 10%
                "inventory": 80, "net_income": 200, "operating_cash_flow": 250,
                "short_loan": 60, "long_term_invest": 35, "total_assets": 2200,
                "goodwill": 110,
            },
            {
                "revenue": 1200, "accounts_receivable": 600,  # AR gap >> 10% again
                "inventory": 130, "net_income": 220, "operating_cash_flow": 150,  # OCF < NI
                "short_loan": 80, "long_term_invest": 40, "total_assets": 2400,
                "goodwill": 120,
            },
        ])
        alerts = detect_anomalies("TEST", data, "测试公司")
        assert len(alerts) > 0
        # HIGH severity should come first
        if any(a.severity == "HIGH" for a in alerts):
            first_high = next(i for i, a in enumerate(alerts) if a.severity == "HIGH")
            first_medium = next((i for i, a in enumerate(alerts) if a.severity == "MEDIUM"), len(alerts))
            assert first_high < first_medium


# ---------------------------------------------------------------------------
# format_alerts
# ---------------------------------------------------------------------------
class TestFormatAlerts:
    def test_empty_alerts(self):
        result = format_alerts([], "测试公司")
        assert "🟢" in result
        assert "未检测到" in result

    def test_with_alerts(self):
        alerts = [AnomalyAlert(
            rule_id="W1.1.1",
            rule_name="测试规则",
            severity="HIGH",
            emoji="🔴",
            ticker="TEST",
            company_name="测试公司",
            period="2025-12-31",
            detail="测试详情",
            metrics={"test": 42},
        )]
        result = format_alerts(alerts, "测试公司")
        assert "🔴" in result
        assert "测试规则" in result
        assert "测试详情" in result
        assert "test=42" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_zero_revenue_no_crash(self):
        data = _make_annual([
            {"revenue": 0, "accounts_receivable": 10},
            {"revenue": 0, "accounts_receivable": 20},
        ])
        alerts = _check_ar_vs_revenue("TEST", data, "测试公司")
        assert alerts == []  # should skip, not crash

    def test_zero_inventory_no_crash(self):
        data = _make_annual([
            {"revenue": 100, "inventory": 0},
            {"revenue": 100, "inventory": 0},
            {"revenue": 100, "inventory": 0},
            {"revenue": 100, "inventory": 0},
        ])
        alerts = _check_inventory_turnover("TEST", data, "测试公司")
        assert alerts == []

    def test_all_none_fields(self):
        data = _make_annual([{}, {}, {}])
        alerts = detect_anomalies("TEST", data, "测试公司")
        assert alerts == []
