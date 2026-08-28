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
    store.add_event(_make_event(affected_tickers=["AAPL"]))
    store.add_event(_make_event(affected_tickers=["TSLA"], title="TSLA Earnings", event_date="2026-07-20"))
    store.add_event(_make_event(affected_tickers=["GOOG"], title="GOOG Earnings", event_date="2026-07-21"))

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
    e1 = store.add_event(_make_event())
    e2 = store.add_event(_make_event())
    assert e1.event_id != e2.event_id
