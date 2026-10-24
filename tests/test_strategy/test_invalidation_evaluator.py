"""失效评估器 + 指标历史表的回归测试。

覆盖 2026-10-14 新增：
  - indicator_history 幂等写入 / 连续红期数判定
  - required_periods_from 对「2季/3个月/1期」的翻译
  - 评估器：单期红 ≠ 失效；连红够期数才触发；无数据不得判失效
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.analysis.leading_indicators import LeadingIndicatorStore
from src.strategy.invalidation_evaluator import (
    evaluate_ticker,
    required_periods_from,
    summarize,
)
from src.strategy.invalidation_watch import WatchSpec


def spec(name, pos, neg, unit="%", leg="测试腿", consecutive="1期"):
    """构造测试用 WatchSpec。

    evaluate_ticker 接受 specs 参数，否则只能评估硬编码 WATCH 表里的
    ticker，新持仓和单测都无从下手。
    """
    return WatchSpec(
        name=name, description=name, source="财报", pos=pos, neg=neg,
        unit=unit, invalidation_leg=leg, consecutive=consecutive,
    )


@pytest.fixture
def store(tmp_path):
    s = LeadingIndicatorStore(db_path=str(tmp_path / "li.duckdb"))
    yield s
    s.close()


def _add(store, ticker, name, pos, neg, unit="%"):
    store.add_indicator(
        ticker=ticker, company_name="测试", indicator_name=name,
        description=name, source="财报", threshold_positive=pos,
        threshold_negative=neg, unit=unit, category="失效观测",
    )


# ---------- 历史表 ----------

def test_history_written_on_update(store):
    _add(store, "T1.HK", "指标A", 10, 0)
    store.update_value("T1.HK", "指标A", -3.0, "2026H1")
    hist = store.get_history("T1.HK", "指标A")
    assert len(hist) == 1
    assert hist[0]["value"] == -3.0
    assert hist[0]["status"] == "negative"


def test_history_idempotent_same_period(store):
    """同一期重复写入覆盖，不产生重复行——否则连续期数会被污染。"""
    _add(store, "T1.HK", "指标A", 10, 0)
    store.update_value("T1.HK", "指标A", -3.0, "2026H1")
    store.update_value("T1.HK", "指标A", -4.0, "2026H1")
    hist = store.get_history("T1.HK", "指标A")
    assert len(hist) == 1
    assert hist[0]["value"] == -4.0


def test_history_sorted_desc(store):
    _add(store, "T1.HK", "指标A", 10, 0)
    for p, v in [("2025A", 5.0), ("2026H1", -2.0), ("2025H1", 8.0)]:
        store.update_value("T1.HK", "指标A", v, p)
    periods = [h["period"] for h in store.get_history("T1.HK", "指标A")]
    assert periods == ["2026H1", "2025H1", "2025A"]


def test_consecutive_negative_counts_from_latest(store):
    _add(store, "T1.HK", "指标A", 10, 0)
    store.update_value("T1.HK", "指标A", 5.0, "2025A")    # 绿
    store.update_value("T1.HK", "指标A", -1.0, "2025H1")  # 红
    store.update_value("T1.HK", "指标A", -2.0, "2026H1")  # 红
    assert store.consecutive_periods_negative("T1.HK", "指标A") == 2


def test_consecutive_negative_stops_at_green(store):
    """中间夹一期绿就断链——不能把历史全算成连续红。"""
    _add(store, "T1.HK", "指标A", 10, 0)
    for p, v in [("2025A", -1.0), ("2025H1", 5.0), ("2026H1", -2.0)]:
        store.update_value("T1.HK", "指标A", v, p)
    assert store.consecutive_periods_negative("T1.HK", "指标A") == 1


def test_record_history_requires_existing_indicator(store):
    with pytest.raises(ValueError):
        store.record_history("NOPE", "不存在", "2026H1", 1.0)


# ---------- 期数翻译 ----------

@pytest.mark.parametrize("text,expected", [
    ("2季", 2), ("3个月", 3), ("1期", 1), ("2期", 2), ("", 1), (None, 1),
])
def test_required_periods_from(text, expected):
    assert required_periods_from(text) == expected


# ---------- 趋势判定 ----------

def test_trend_bad_direction_parses():
    from src.strategy.invalidation_evaluator import trend_bad_direction
    assert trend_bad_direction("不良率/信贷成本连续两季上升") == "up"
    assert trend_bad_direction("净负债率上升（需与NOI同时）") == "up"
    assert trend_bad_direction("车型定点数连续两季净减少") == "down"
    assert trend_bad_direction("海外同店连续两季负增长") == "down"
    assert trend_bad_direction("云收入连续两季减速") == "down"
    # 水平型腿不该被当成趋势腿
    assert trend_bad_direction("毛利率跌破20%且无盈利路径") is None
    assert trend_bad_direction("每股净资产不再覆盖市值") is None
    assert trend_bad_direction("") is None


def test_trend_leg_triggers_even_when_level_is_green(store):
    """LX 不良率的真实教训：3.6% 还不到极端水平（水平判绿），但已连升 3 季。
    趋势腿必须能在这个情况下触发，否则整条失效条件永远抓不到。"""
    _add(store, "T1.HK", "不良率", 3, 5, "%")
    s = spec("不良率", 3, 5, "%", "不良率/信贷成本连续两季上升", "2季")
    for p, v in [("2025-09-30", 3.0), ("2025-12-31", 3.1),
                 ("2026-03-31", 3.5), ("2026-06-30", 3.6)]:
        store.update_value("T1.HK", "不良率", v, p)

    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.trend_direction == "up"
    assert ev.trend_streak == 3          # 3.0→3.1→3.5→3.6 三次上升
    assert ev.triggered is True          # 需 2 期，已 3 期
    assert ev.judged_by == "trend"
    # 水平上还没到 neg 阈值 5，所以红灯计数是 0 —— 这正是趋势判定存在的理由
    assert ev.red_streak == 0


def test_trend_leg_not_triggered_with_only_one_rise(store):
    _add(store, "T1.HK", "不良率", 3, 5, "%")
    s = spec("不良率", 3, 5, "%", "不良率连续两季上升", "2季")
    store.update_value("T1.HK", "不良率", 3.0, "2025-12-31")
    store.update_value("T1.HK", "不良率", 3.6, "2026-06-30")   # 只上升 1 次
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.trend_streak == 1
    assert ev.triggered is False


def test_trend_streak_resets_when_direction_reverses(store):
    """升-升-降-升 → 连续上升只算最后一次的 1 期。"""
    _add(store, "T1.HK", "不良率", 3, 5, "%")
    s = spec("不良率", 3, 5, "%", "不良率连续两季上升", "2季")
    for p, v in [("2025-06-30", 3.0), ("2025-12-31", 3.4),   # 升
                 ("2026-03-31", 3.2),                        # 降 → 断链
                 ("2026-06-30", 3.5)]:                       # 升 1 次
        store.update_value("T1.HK", "不良率", v, p)
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.trend_streak == 1
    assert ev.triggered is False


def test_flat_values_do_not_break_trend(store):
    """持平既不计入也不打断，避免小数抖动把趋势判没。"""
    _add(store, "T1.HK", "不良率", 3, 5, "%")
    s = spec("不良率", 3, 5, "%", "不良率连续两季上升", "2季")
    for p, v in [("2025-06-30", 3.0), ("2025-12-31", 3.2),
                 ("2026-03-31", 3.2),                        # 持平
                 ("2026-06-30", 3.5)]:
        store.update_value("T1.HK", "不良率", v, p)
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.trend_streak == 2          # 3.0→3.2 算1次，3.2→3.2 持平跳过，3.2→3.5 算1次
    assert ev.triggered is True


def test_level_leg_still_works_for_threshold_conditions(store):
    """「跌破20%」这类水平腿不受趋势逻辑影响。"""
    _add(store, "T1.HK", "毛利率", 25, 20, "%")
    s = spec("毛利率", 25, 20, "%", "毛利率跌破20%且无盈利路径", "1期")
    store.update_value("T1.HK", "毛利率", 18.0, "2026-06-30")
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.status == "negative"
    assert ev.triggered is False         # 1期腿单期红不自动判失效
    assert ev.judged_by == "level"


# ---------- 评估器 ----------

def test_single_period_red_is_not_triggered(store):
    """1期腿红 = 需人工判定，不自动判失效（速腾OCF就是这种情况）。"""
    _add(store, "T1.HK", "OCF", 0, -1, "亿元")
    store.update_value("T1.HK", "OCF", -4.2, "2026-06-30")
    ev = evaluate_ticker(store, "T1.HK", "测试",
                         specs=[spec("OCF", 0, -1, "亿元", "盈利路径", "1期")])[0]
    assert ev.status == "negative"
    assert ev.red_streak == 1
    assert ev.triggered is False


def test_two_period_leg_triggers_on_second_red(store):
    _add(store, "T1.HK", "同店增速", 5, 0)
    s = spec("同店增速", 5, 0, leg="海外同店连续两季负增长", consecutive="2季")
    store.update_value("T1.HK", "同店增速", -1.0, "2026H1")   # 第1期红
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.triggered is False          # 单期红不触发

    store.update_value("T1.HK", "同店增速", -2.0, "2026A")    # 第2期红
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.triggered is True           # 连红2期 = 失效
    assert ev.red_streak == 2


def test_three_period_leg_needs_three(store):
    _add(store, "T1.HK", "交付同比", 10, 0)
    s = spec("交付同比", 10, 0, leg="SU7月交付连续3个月同比下滑", consecutive="3个月")
    for p, v in [("2026-04", -1.0), ("2026-05", -2.0)]:
        store.update_value("T1.HK", "交付同比", v, p)
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.consecutive == "3个月"
    assert ev.required_periods == 3
    assert ev.triggered is False          # 只连红2期

    store.update_value("T1.HK", "交付同比", -3.0, "2026-06")
    assert evaluate_ticker(store, "T1.HK", specs=[s])[0].triggered is True


def test_recovered_leg_resets_streak(store):
    """红两期后转绿，再红一期 → 不应仍判触发。"""
    _add(store, "T1.HK", "同店增速", 5, 0)
    s = spec("同店增速", 5, 0, consecutive="2季")
    for p, v in [("2025A", -1.0), ("2026H1", -2.0), ("2026Q3", 3.0), ("2026Q4", -1.0)]:
        store.update_value("T1.HK", "同店增速", v, p)
    ev = evaluate_ticker(store, "T1.HK", specs=[s])[0]
    assert ev.red_streak == 1
    assert ev.triggered is False


def test_unknown_when_no_value(store):
    _add(store, "T1.HK", "手术量增速", 20, 0)
    ev = evaluate_ticker(store, "T1.HK",
                         specs=[spec("手术量增速", 20, 0, consecutive="2季")])[0]
    assert ev.status == "unknown"
    assert ev.value is None
    assert ev.triggered is False


def test_lower_is_better_handled(store):
    """存货周转天数：阈值 pos<neg 表示越低越好。"""
    _add(store, "T1.HK", "存货周转天数", 50, 80, "天")
    store.update_value("T1.HK", "存货周转天数", 95.0, "2026A")
    ev = evaluate_ticker(store, "T1.HK",
                         specs=[spec("存货周转天数", 50, 80, "天")])[0]
    assert ev.status == "negative"


def test_summarize_counts(store):
    _add(store, "T1.HK", "A", 10, 0)
    _add(store, "T1.HK", "B", 5, 0)
    _add(store, "T1.HK", "C", 20, 0)      # 无值 → unknown
    store.update_value("T1.HK", "A", 15.0, "2026A")   # 绿
    store.update_value("T1.HK", "B", -1.0, "2026A")   # 红
    s = summarize(evaluate_ticker(
        store, "T1.HK",
        specs=[spec("A", 10, 0), spec("B", 5, 0), spec("C", 20, 0)],
    ))
    assert s == {"total": 3, "triggered": 0, "red": 1, "neutral": 0,
                 "positive": 1, "unknown": 1, "tickers": 1}


def test_falls_back_to_watch_table():
    """不传 specs 时仍从 WATCH 表取——验证与现有持仓的接线没断。"""
    from src.strategy.invalidation_watch import WATCH
    ticker, _, specs = WATCH[0]
    assert specs, "WATCH 首个持仓应有观测指标"
    assert all(s.name for s in specs)
