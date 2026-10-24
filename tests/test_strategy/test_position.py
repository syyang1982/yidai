"""Tests for src/strategy/position.py — 持仓实体 + FIFO."""

from src.strategy.decision import DecisionLog, DecisionRecord
from src.strategy.position import PositionBook


def _buy(ticker, shares, price, date, thesis="长期看好", currency="HKD"):
    return DecisionRecord(
        ticker=ticker,
        company_name=ticker,
        market="HK",
        action="BUY",
        shares=shares,
        price=price,
        currency=currency,
        thesis=thesis,
        decision_date=date,
    )


def _sell(ticker, shares, price, date):
    return DecisionRecord(
        ticker=ticker,
        company_name=ticker,
        market="HK",
        action="SELL",
        shares=shares,
        price=price,
        currency="HKD",
        decision_date=date,
    )


def test_open_and_add_same_position():
    book = PositionBook(":memory:")
    r1 = _buy("01810.HK", 1000, 30.0, "2026-04-19")
    r1.decision_id = "d1"
    out = book.apply_fill(r1, invalidation="汽车交付失速", require_invalidation=True)
    assert out["accepted"]
    pos = out["position"]
    assert pos.shares == 1000
    assert pos.avg_cost == 30.0
    assert r1.position_id == pos.position_id

    r2 = _buy("01810.HK", 400, 29.0, "2026-07-31")
    r2.decision_id = "d2"
    out2 = book.apply_fill(r2)
    assert out2["position"].position_id == pos.position_id
    assert out2["position"].shares == 1400
    assert abs(out2["position"].avg_cost - (1000 * 30 + 400 * 29) / 1400) < 1e-9


def test_new_position_requires_invalidation():
    book = PositionBook(":memory:")
    rec = _buy("01810.HK", 1000, 30.0, "2026-04-19")
    out = book.apply_fill(rec, require_invalidation=True)
    assert out["accepted"] is False
    assert any("失效条件" in v for v in out["violations"])


def test_fifo_sell_then_close():
    book = PositionBook(":memory:")
    r1 = _buy("03896.HK", 2000, 5.0, "2026-04-19")
    r1.decision_id = "a"
    book.apply_fill(r1, invalidation="合同负债下滑", require_invalidation=True)
    r2 = _buy("03896.HK", 2000, 6.0, "2026-08-06")
    r2.decision_id = "b"
    book.apply_fill(r2)
    pos = book.get_open("03896.HK")
    assert pos.shares == 4000
    assert abs(pos.avg_cost - 5.5) < 1e-9

    s1 = _sell("03896.HK", 2000, 6.92, "2026-08-20")
    s1.decision_id = "c"
    book.apply_fill(s1)
    pos = book.get_open("03896.HK")
    assert pos is not None
    assert pos.shares == 2000
    assert abs(pos.avg_cost - 6.0) < 1e-9  # first lot consumed

    s2 = _sell("03896.HK", 2000, 6.15, "2026-08-21")
    s2.decision_id = "d"
    book.apply_fill(s2)
    assert book.get_open("03896.HK") is None
    closed = book.list_all(ticker="03896.HK", status="closed")
    assert len(closed) == 1
    assert closed[0].shares == 0


def test_rebuy_after_close_is_new_position():
    book = PositionBook(":memory:")
    r1 = _buy("1361.HK", 1000, 4.5, "2026-06-17")
    r1.decision_id = "x1"
    book.apply_fill(r1, invalidation="品牌力持续走弱", require_invalidation=True)
    pid = r1.position_id
    s1 = _sell("1361.HK", 1000, 4.4, "2026-09-07")
    s1.decision_id = "x2"
    book.apply_fill(s1)
    r2 = _buy("1361.HK", 2000, 4.0, "2026-09-08")
    r2.decision_id = "x3"
    book.apply_fill(r2, invalidation="新一轮失效条件", require_invalidation=True)
    assert r2.position_id != pid
    assert book.get_open("1361.HK").shares == 2000


def test_rebuild_from_decision_log():
    log = DecisionLog(":memory:")
    book = PositionBook(conn=log.conn)
    log.record(_buy("01810.HK", 1000, 30.0, "2026-04-19"))
    log.record(_buy("01810.HK", 400, 29.0, "2026-07-31"))
    stats = book.rebuild_from_decisions(log)
    assert stats["open"] == 1
    pos = book.get_open("01810.HK")
    assert pos.shares == 1400
    recs = log.list_decisions(ticker="01810.HK")
    assert all(r.position_id == pos.position_id for r in recs)


def test_rebuild_is_idempotent():
    """rebuild 重放决策不能让股数翻倍（2026-09-25 修的坑）。"""
    log = DecisionLog(":memory:")
    book = PositionBook(conn=log.conn)
    log.record(_buy("01810.HK", 1000, 30.0, "2026-04-19"))
    log.record(_buy("01810.HK", 400, 29.0, "2026-07-31"))
    log.record(_sell("01810.HK", 200, 32.0, "2026-08-01"))

    book.rebuild_from_decisions(log)
    first = book.get_open("01810.HK")
    state = (first.shares, round(first.avg_cost, 6), len(book.list_all()))

    book.rebuild_from_decisions(log)
    second = book.get_open("01810.HK")
    assert (second.shares, round(second.avg_cost, 6), len(book.list_all())) == state
    assert second.shares == 1200


def test_cny_fill_is_booked_in_hkd_for_hk_position():
    """港股持仓成本一律以港币记账，人民币成交价按汇率折算。"""
    book = PositionBook(":memory:")
    r = _buy("09896.HK", 1000, 38.277, "2026-04-19", currency="CNY")
    r.decision_id = "m1"
    out = book.apply_fill(r, invalidation="海外同店连续负增长", require_invalidation=True)
    pos = out["position"]
    assert pos.currency == "HKD"
    assert abs(pos.avg_cost - 38.277 / 0.872489) < 1e-6


def test_reconcile_writes_authoritative_lots_and_rebuild_skips():
    """对账写入券商口径批次，rebuild 不得覆盖。"""
    log = DecisionLog(":memory:")
    book = PositionBook(conn=log.conn)
    log.record(_buy("03896.HK", 2000, 5.369, "2026-04-19"))
    log.record(_buy("03896.HK", 4000, 4.93, "2026-07-17"))
    book.rebuild_from_decisions(log)
    assert book.get_open("03896.HK").shares == 6000

    pos = book.reconcile(
        "03896.HK",
        [(8000, 4.708, "CNY"), (4000, 5.01, "HKD")],
        note="券商口径",
    )
    assert pos is not None
    assert pos.shares == 12000
    assert pos.currency == "HKD"
    expected = (8000 * 4.708 / 0.872489 + 4000 * 5.01) / 12000
    assert abs(pos.avg_cost - expected) < 1e-6

    stats = book.rebuild_from_decisions(log)
    assert stats["reconciled"] == 1
    assert stats["skipped_reconciled"] == 2
    after = book.get_open("03896.HK")
    assert after.shares == 12000
    assert abs(after.avg_cost - expected) < 1e-6
    assert "已对账" in book.to_markdown(after)
