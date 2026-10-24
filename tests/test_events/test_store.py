"""Tests for the EventStore."""

import os
import pytest

from src.events.models import MarketEvent
from src.events.store import EventStore


@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "test_events.duckdb")
    s = EventStore(db_path=db)
    yield s
    s.close()


def _make_event(**kwargs) -> MarketEvent:
    defaults = {
        "event_type": "earnings",
        "title": "AAPL Q2 Earnings",
        "description": "Apple quarterly earnings",
        "event_date": "2026-07-15",
        "affected_tickers": ["AAPL", "QQQ"],
        "sector": "tech",
        "impact_level": "high",
        "impact_direction": "positive",
        "status": "pending",
    }
    defaults.update(kwargs)
    return MarketEvent(**defaults)


def test_add_and_retrieve(store):
    e = _make_event()
    result = store.add_event(e)
    assert result.event_id != ""
    assert result.created_at != ""

    fetched = store.get_by_id(result.event_id)
    assert fetched is not None
    assert fetched.title == "AAPL Q2 Earnings"
    assert fetched.affected_tickers == ["AAPL", "QQQ"]
    assert fetched.notified is False


def test_filter_by_ticker(store):
    # 事件日期必须相对「今天」生成——写死日期会在时间流逝后落到过去，
    # get_upcoming() 就一条也查不出来（2026-09-22 实测 2026-07-20 已成历史）。
    from datetime import date, timedelta   # 局部导入：避免改动文件头
    today = date.today()
    store.add_event(_make_event(
        affected_tickers=["AAPL"], event_date=str(today + timedelta(days=9))))
    store.add_event(_make_event(
        affected_tickers=["TSLA"], title="TSLA Earnings",
        event_date=str(today + timedelta(days=10))))
    store.add_event(_make_event(
        affected_tickers=["GOOG"], title="GOOG Earnings",
        event_date=str(today + timedelta(days=11))))

    results = store.get_upcoming(days=30, tickers=["TSLA"])
    assert len(results) == 1
    assert results[0].title == "TSLA Earnings"


def test_filter_by_type(store):
    store.add_event(_make_event(event_type="earnings"))
    store.add_event(_make_event(event_type="dividend", title="DIV Event", event_date="2026-07-20"))
    store.add_event(_make_event(event_type="macro", title="Macro Event", event_date="2026-07-21"))

    results = store.get_by_type("earnings")
    assert len(results) == 1
    assert results[0].event_type == "earnings"


def test_mark_notified(store):
    e = store.add_event(_make_event())
    assert e.notified is False
    ok = store.mark_notified(e.event_id)
    assert ok is True
    fetched = store.get_by_id(e.event_id)
    assert fetched.notified is True


def test_update_impact(store):
    e = store.add_event(_make_event(impact_level="low"))
    ok = store.update_impact(e.event_id, impact_level="high", impact_direction="negative", impact_analysis="Sell pressure expected")
    assert ok is True
    fetched = store.get_by_id(e.event_id)
    assert fetched.impact_level == "high"
    assert fetched.impact_direction == "negative"
    assert fetched.impact_analysis == "Sell pressure expected"


def test_delete_event(store):
    e = store.add_event(_make_event())
    assert store.get_by_id(e.event_id) is not None
    ok = store.delete_event(e.event_id)
    assert ok is True
    assert store.get_by_id(e.event_id) is None


def test_auto_generated_id(store):
    # 两条不同事件 → 各自自动生成 event_id
    e1 = store.add_event(_make_event())
    e2 = store.add_event(_make_event(title="MSFT Q2 Earnings"))
    assert e1.event_id != e2.event_id
    assert e1.event_id != "" and e2.event_id != ""


def test_duplicate_event_is_skipped(store):
    # 同业务键(类型+标题+日期+来源)重复添加 → 跳过并返回 None，不产生第二行
    first = store.add_event(_make_event())
    assert first is not None
    dup = store.add_event(_make_event())
    assert dup is None
    rows = store.get_all()
    assert len(rows) == 1


def test_dedup_can_be_disabled(store):
    # dedup=False 时仍允许多行（供 --refresh 重建内置日历等场景使用）
    a = store.add_event(_make_event(), dedup=False)
    b = store.add_event(_make_event(), dedup=False)
    assert a is not None and b is not None
    assert len(store.get_all()) == 2
    # dedupe() 能把历史重复行压回一条
    removed = store.dedupe()
    assert removed == 1
    assert len(store.get_all()) == 1


def test_get_by_type_accepts_days(store):
    # E3 回归：manage.py 调 get_by_type(type, days=N)，修复前签名不收 days 直接 TypeError
    from datetime import date, timedelta  # 局部导入：保持文件头不变
    future = (date.today() + timedelta(days=3)).isoformat()
    later = (date.today() + timedelta(days=90)).isoformat()
    past = (date.today() - timedelta(days=10)).isoformat()
    store.add_event(_make_event(title="近期宏观", event_type="macro", event_date=future, source="内置日历"))
    store.add_event(_make_event(title="远期宏观", event_type="macro", event_date=later, source="内置日历"))
    store.add_event(_make_event(title="过期宏观", event_type="macro", event_date=past, source="内置日历"))

    within = store.get_by_type("macro", days=30)
    titles = {e.title for e in within}
    assert "近期宏观" in titles      # 在窗口内
    assert "远期宏观" not in titles   # 超出 days 窗口
    assert "过期宏观" not in titles   # 已过去

    assert len(store.get_by_type("macro")) == 3  # 不传 days 保持原全量语义
    assert store.get_by_type("earnings", days=30) == []
