"""Missing-data BUY gate: skipped health/cashflow checks must not fire BUY."""

from src.analysis.scorer import collect_buy_blocking_gaps, _build_cashflow_data


def test_collect_gaps_when_hk_fields_missing():
    gaps = collect_buy_blocking_gaps(
        health_input={"debt_ratio": 0.4},
        cf_input={"operating_cash_flow": 1e8, "free_cash_flow": None},
    )
    assert "current_ratio" in gaps
    assert "interest_bearing_debt" in gaps
    assert "free_cash_flow" in gaps


def test_collect_gaps_empty_when_complete():
    gaps = collect_buy_blocking_gaps(
        health_input={
            "debt_ratio": 0.4,
            "current_ratio": 1.5,
            "interest_bearing_debt_ratio": 0.1,
        },
        cf_input={"operating_cash_flow": 1e8, "free_cash_flow": 5e7},
    )
    assert gaps == []


def test_fcf_derived_from_ocf_minus_capex():
    data = _build_cashflow_data(
        {"operating_cash_flow": 100, "net_income": 80, "capex": -20},
        None,
    )
    assert data["free_cash_flow"] == 80
