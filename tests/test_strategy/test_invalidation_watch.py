"""失效观测表：12 个持仓各有指标，种子值能算出红黄绿。"""

from src.analysis.leading_indicators import LeadingIndicatorStore, _calculate_status
from src.strategy.invalidation_watch import WATCH, all_tickers, specs_for, sync, snapshot_for_ticker


def test_twelve_open_tickers_covered():
    expected = {
        "01810.HK", "02020.HK", "02252.HK", "02498.HK", "03888.HK", "03896.HK",
        "09626.HK", "09896.HK", "09988.HK", "09999.HK", "LX", "SGP.AX",
    }
    assert set(all_tickers()) == expected
    for t in expected:
        specs = specs_for(t)
        assert 1 <= len(specs) <= 3


def test_inventory_days_lower_is_better():
    # 名创存货周转天数: pos=50 neg=80
    assert _calculate_status(40, 50, 80) == "positive"
    assert _calculate_status(90, 50, 80) == "negative"
    assert _calculate_status(60, 50, 80) == "neutral"


def test_ocf_negative_threshold():
    assert _calculate_status(341.4, 0, -1) == "positive"
    assert _calculate_status(-5.8, 0, -1) == "negative"
    assert _calculate_status(-0.2, 0, -1) == "neutral"


def test_sync_seeds_and_status(tmp_path):
    db = str(tmp_path / "li.duckdb")
    store = LeadingIndicatorStore(db)
    stats = sync(store)
    assert stats["registered"] == sum(len(s) for _, _, s in WATCH)
    assert stats["seeded"] >= 8
    rows = snapshot_for_ticker(store, "01810.HK")
    ocf = next(r for r in rows if r["name"] == "经营现金流")
    assert ocf["status"] == "positive"
    gm = next(r for r in snapshot_for_ticker(store, "02498.HK") if r["name"] == "毛利率")
    assert gm["status"] == "positive"
    office = next(r for r in snapshot_for_ticker(store, "03888.HK") if r["name"] == "办公软件收入同比")
    assert office["status"] == "negative"
