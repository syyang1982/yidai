"""Tests for src/strategy/analog.py — 决策时类比检索."""

from src.strategy.analog import find_analogs
from src.strategy.decision import DecisionLog, DecisionRecord


def _rec(**kwargs):
    base = dict(
        ticker="01810.HK",
        company_name="小米",
        market="HK",
        action="BUY",
        shares=1000,
        price=30.0,
        reason="低位加仓摊低成本",
        reason_category="低位机会",
        decision_date="2026-04-19",
        confidence_level=4,
    )
    base.update(kwargs)
    return DecisionRecord(**base)


def test_find_analogs_same_ticker_and_playbook():
    log = DecisionLog(":memory:")
    log.record(_rec(decision_id="old1", actual_return_pct=12.0, actual_price_6m=33.6))
    log.record(_rec(
        decision_id="old2",
        ticker="02020.HK",
        company_name="安踏",
        reason_category="低位机会",
        actual_return_pct=-8.0,
        actual_price_6m=70.0,
        decision_date="2026-05-01",
    ))
    log.record(_rec(
        decision_id="other",
        ticker="09988.HK",
        reason_category="组合再平衡",
        actual_return_pct=5.0,
        actual_price_6m=100.0,
    ))

    pending = _rec(decision_id="new", decision_date="2026-09-13")
    report = find_analogs(log, pending, limit=4)
    ids = {m.decision_id for m in report.matches}
    assert "old1" in ids
    assert "old2" in ids
    assert "other" not in ids
    assert report.playbook_n == 2
    assert report.playbook_reviewed == 2
    assert report.playbook_hit_rate == 0.5
    text = report.format_text()
    assert "类比检索" in text
    assert "低位机会" in text


def test_confidence_calibration_separate_from_playbook():
    log = DecisionLog(":memory:")
    log.record(_rec(
        decision_id="c1",
        ticker="A",
        reason_category="组合再平衡",
        confidence_level=5,
        actual_return_pct=-15.0,
        actual_price_6m=10,
    ))
    log.record(_rec(
        decision_id="c2",
        ticker="B",
        reason_category="组合再平衡",
        confidence_level=5,
        actual_return_pct=20.0,
        actual_price_6m=10,
    ))
    pending = _rec(reason_category="低位机会", confidence_level=5)
    report = find_analogs(log, pending)
    assert report.confidence_n == 2
    assert report.confidence_hit_rate == 0.5


def test_live_record_rejects_buy_without_counter_argument():
    log = DecisionLog(":memory:")
    rec = _rec(counter_argument="", confidence_level=4)
    result = log.record(rec, enforce_process=True)
    assert result["accepted"] is False
    rec.counter_argument = "汽车交付不及预期"
    rec.decision_id = ""
    result = log.record(rec, enforce_process=True)
    assert result["accepted"] is True
