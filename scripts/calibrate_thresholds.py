"""
W2.3.1 — 信号阈值校准模块

基于 signal_records 的历史数据，分析不同评分阈值下的信号准确率，
推荐最优的 BUY/REDUCE/HOLD 切分点。

核心思路:
    当前: A(23+) B(18+) C(13+) D(8+) F(<8) — 基于直觉设定
    校准: 遍历所有可能的总分阈值，找到 BUY准确率最高 + REDUCE准确率最高 的切分点

用法:
    cd ~/.hermes/yidai
    python scripts/calibrate_thresholds.py              # 生成报告
    python scripts/calibrate_thresholds.py --apply      # 更新 scorer.py 阈值
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb

DEFAULT_DB = PROJECT_ROOT / "db" / "signals.duckdb"


def load_signals(db_path: Path) -> list[dict]:
    """加载信号记录，解析 JSON 字段。"""
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT signal_id, ticker, signal_type, signal_date, "
            "company_state, total_score, grade, dimension_scores, "
            "actual_6m, time_window_prices "
            "FROM signal_records ORDER BY signal_date"
        ).fetchall()

        col_names = [
            "signal_id", "ticker", "signal_type", "signal_date",
            "company_state", "total_score", "grade", "dimension_scores",
            "actual_6m", "time_window_prices",
        ]
    finally:
        conn.close()

    records = []
    for row in rows:
        rec = dict(zip(col_names, row))
        # 解析 JSON 字段
        for col in ["company_state", "dimension_scores", "actual_6m", "time_window_prices"]:
            val = rec.get(col)
            if isinstance(val, str) and val:
                try:
                    rec[col] = json.loads(val)
                except json.JSONDecodeError:
                    rec[col] = None

        # 提取 signal_price
        cs = rec.get("company_state") or {}
        rec["signal_price"] = cs.get("price") if isinstance(cs, dict) else None

        # 提取 current_price (from actual_6m)
        actual = rec.get("actual_6m") or {}
        if isinstance(actual, dict):
            rec["current_price"] = actual.get("actual_price")
        else:
            rec["current_price"] = None

        records.append(rec)

    return records


def calculate_direction(signal_type: str, signal_price: float, current_price: float) -> Optional[bool]:
    """计算方向正确性。True=正确, False=错误, None=无法判断。"""
    if not signal_price or not current_price or signal_price == 0:
        return None
    ret = (current_price - signal_price) / signal_price
    if signal_type == "BUY":
        return ret > 0
    elif signal_type == "REDUCE":
        return ret < 0
    elif signal_type == "HOLD":
        return abs(ret) < 0.10
    return None


def compute_return(signal_price: float, current_price: float) -> Optional[float]:
    """计算收益率。"""
    if not signal_price or signal_price == 0:
        return None
    return (current_price - signal_price) / signal_price


def calibrate(
    db_path: Path = DEFAULT_DB,
    window_days: Optional[int] = None,
) -> dict:
    """执行阈值校准分析。

    Args:
        db_path: DuckDB 路径
        window_days: 如果指定，使用 time_window_prices[N] 作为 current_price

    Returns:
        校准结果 dict
    """
    records = load_signals(db_path)

    # 过滤有价格数据的记录
    valid = []
    for rec in records:
        # 确定 current_price
        if window_days:
            twp = rec.get("time_window_prices") or {}
            if isinstance(twp, dict):
                wp = twp.get(str(window_days))
                if wp and wp.get("price"):
                    rec["_eval_price"] = wp["price"]
                else:
                    continue
            else:
                continue
        else:
            if rec.get("current_price"):
                rec["_eval_price"] = rec["current_price"]
            else:
                continue

        if rec.get("signal_price") and rec["_eval_price"]:
            valid.append(rec)

    if not valid:
        return {"error": "没有可用的价格数据", "total_signals": len(records)}

    # ── 1. 按总分区间统计准确率 ──
    # 遍历所有可能的阈值 (0-35)
    score_range = range(0, 36)

    buy_stats = {}      # {threshold: {total, correct, avg_return}}
    reduce_stats = {}

    for threshold in score_range:
        buy_t, buy_c, buy_rets = 0, 0, []
        red_t, red_c, red_rets = 0, 0, []

        for rec in valid:
            score = rec.get("total_score", 0)
            sig_type = rec.get("signal_type", "")
            sig_price = rec["signal_price"]
            cur_price = rec["_eval_price"]
            direction = calculate_direction(sig_type, sig_price, cur_price)
            ret = compute_return(sig_price, cur_price)

            if sig_type == "BUY" and score >= threshold:
                buy_t += 1
                if direction:
                    buy_c += 1
                if ret is not None:
                    buy_rets.append(ret)

            if sig_type == "REDUCE" and score <= threshold:
                red_t += 1
                if direction:
                    red_c += 1
                if ret is not None:
                    red_rets.append(ret)

        buy_stats[threshold] = {
            "total": buy_t,
            "correct": buy_c,
            "accuracy": buy_c / buy_t if buy_t > 0 else 0,
            "avg_return": sum(buy_rets) / len(buy_rets) if buy_rets else 0,
        }
        reduce_stats[threshold] = {
            "total": red_t,
            "correct": red_c,
            "accuracy": red_c / red_t if red_t > 0 else 0,
            "avg_return": sum(red_rets) / len(red_rets) if red_rets else 0,
        }

    # ── 2. 找最优阈值 ──
    # BUY: 准确率 > 55% 且样本量 > 10 的最高准确率
    best_buy_threshold = None
    best_buy_acc = 0
    for t in score_range:
        s = buy_stats[t]
        if s["total"] >= 10 and s["accuracy"] > best_buy_acc:
            best_buy_acc = s["accuracy"]
            best_buy_threshold = t

    # REDUCE: 准确率 > 55% 且样本量 > 10 的最高准确率
    best_reduce_threshold = None
    best_reduce_acc = 0
    for t in score_range:
        s = reduce_stats[t]
        if s["total"] >= 10 and s["accuracy"] > best_reduce_acc:
            best_reduce_acc = s["accuracy"]
            best_reduce_threshold = t

    # ── 3. 按维度分析预测力 ──
    dim_analysis = defaultdict(lambda: {"high": {"t": 0, "c": 0, "rets": []},
                                         "low": {"t": 0, "c": 0, "rets": []}})

    for rec in valid:
        dims = rec.get("dimension_scores") or {}
        if not isinstance(dims, dict):
            continue
        sig_type = rec.get("signal_type", "")
        direction = calculate_direction(sig_type, rec["signal_price"], rec["_eval_price"])
        ret = compute_return(rec["signal_price"], rec["_eval_price"])

        for dim_name, score in dims.items():
            bucket = "high" if score >= 3 else "low"
            da = dim_analysis[dim_name][bucket]
            da["t"] += 1
            if direction:
                da["c"] += 1
            if ret is not None:
                da["rets"].append(ret)

    dim_results = {}
    for dim_name, data in dim_analysis.items():
        h = data["high"]
        l = data["low"]
        h_acc = h["c"] / h["t"] if h["t"] > 0 else 0
        l_acc = l["c"] / l["t"] if l["t"] > 0 else 0
        dim_results[dim_name] = {
            "high_accuracy": h_acc,
            "low_accuracy": l_acc,
            "predictive_power": h_acc - l_acc,
            "high_count": h["t"],
            "low_count": l["t"],
            "high_avg_return": sum(h["rets"]) / len(h["rets"]) if h["rets"] else 0,
            "low_avg_return": sum(l["rets"]) / len(l["rets"]) if l["rets"] else 0,
        }

    # ── 4. 当前等级分布 ──
    grade_current = defaultdict(lambda: {"total": 0, "correct": 0, "returns": []})
    for rec in valid:
        grade = rec.get("grade", "?")
        sig_type = rec.get("signal_type", "")
        direction = calculate_direction(sig_type, rec["signal_price"], rec["_eval_price"])
        ret = compute_return(rec["signal_price"], rec["_eval_price"])
        g = grade_current[grade]
        g["total"] += 1
        if direction:
            g["correct"] += 1
        if ret is not None:
            g["returns"].append(ret)

    grade_report = {}
    for grade, g in sorted(grade_current.items()):
        grade_report[grade] = {
            "total": g["total"],
            "accuracy": g["correct"] / g["total"] if g["total"] > 0 else 0,
            "avg_return": sum(g["returns"]) / len(g["returns"]) if g["returns"] else 0,
        }

    return {
        "total_signals": len(records),
        "valid_signals": len(valid),
        "window_days": window_days,
        "buy_threshold_analysis": buy_stats,
        "reduce_threshold_analysis": reduce_stats,
        "best_buy_threshold": best_buy_threshold,
        "best_buy_accuracy": best_buy_acc,
        "best_reduce_threshold": best_reduce_threshold,
        "best_reduce_accuracy": best_reduce_acc,
        "dimension_analysis": dim_results,
        "current_grade_distribution": grade_report,
    }


def format_report(result: dict) -> str:
    """格式化校准报告。"""
    sep = "=" * 60
    thin = "─" * 56

    lines = [
        sep,
        "  🎯 信号阈值校准报告",
        sep,
        f"\n  总信号数: {result['total_signals']}",
        f"  有效信号: {result['valid_signals']}",
    ]
    if result.get("window_days"):
        lines.append(f"  时间窗口: {result['window_days']}天")

    # 当前等级分布
    lines += ["", f"  {thin}", "  📊 当前等级分布 (A/B/C/D/F)", f"  {thin}"]
    lines.append("  等级   样本   准确率    平均收益")
    lines.append(f"  {thin}")
    for grade, g in sorted(result.get("current_grade_distribution", {}).items()):
        icon = {"A": "🟢", "B": "🟡"}.get(grade, "🔴")
        lines.append(
            f"  {icon} {grade:<5s} {g['total']:>4d}   "
            f"{g['accuracy']*100:>5.1f}%   {g['avg_return']*100:>+7.2f}%"
        )

    # BUY 阈值分析
    buy_best = result.get("best_buy_threshold")
    buy_acc = result.get("best_buy_accuracy", 0)
    lines += [
        "",
        f"  {thin}",
        f"  🟢 BUY 信号阈值分析 (当前: score >= 18)",
        f"  {thin}",
        f"  推荐阈值: {buy_best} (准确率 {buy_acc*100:.1f}%)" if buy_best else "  无推荐",
        "",
        "  阈值   样本   正确   准确率    平均收益",
        f"  {thin}",
    ]
    # 显示关键阈值点
    buy_stats = result.get("buy_threshold_analysis", {})
    for t in [8, 10, 13, 15, 18, 20, 23, 25, 28]:
        s = buy_stats.get(t, {})
        if s.get("total", 0) > 0:
            marker = " ◀ 推荐" if t == buy_best else ""
            lines.append(
                f"  {t:>3d}    {s['total']:>4d}   {s['correct']:>4d}   "
                f"{s['accuracy']*100:>5.1f}%   {s['avg_return']*100:>+7.2f}%{marker}"
            )

    # REDUCE 阈值分析
    red_best = result.get("best_reduce_threshold")
    red_acc = result.get("best_reduce_accuracy", 0)
    lines += [
        "",
        f"  {thin}",
        f"  🔴 REDUCE 信号阈值分析 (当前: score <= 8)",
        f"  {thin}",
        f"  推荐阈值: {red_best} (准确率 {red_acc*100:.1f}%)" if red_best else "  无推荐",
        "",
        "  阈值   样本   正确   准确率    平均收益",
        f"  {thin}",
    ]
    red_stats = result.get("reduce_threshold_analysis", {})
    for t in [5, 8, 10, 13, 15, 18, 20]:
        s = red_stats.get(t, {})
        if s.get("total", 0) > 0:
            marker = " ◀ 推荐" if t == red_best else ""
            lines.append(
                f"  {t:>3d}    {s['total']:>4d}   {s['correct']:>4d}   "
                f"{s['accuracy']*100:>5.1f}%   {s['avg_return']*100:>+7.2f}%{marker}"
            )

    # 维度预测力
    dims = result.get("dimension_analysis", {})
    if dims:
        lines += [
            "",
            f"  {thin}",
            "  🔬 维度预测力排名",
            f"  {thin}",
            "  维度        预测力  高分准确率  低分准确率  高分收益  低分收益",
            f"  {thin}",
        ]
        sorted_dims = sorted(dims.items(), key=lambda x: x[1]["predictive_power"], reverse=True)
        for name, d in sorted_dims:
            pp = d["predictive_power"]
            icon = "🟢" if pp > 0.05 else "🟡" if pp > -0.05 else "🔴"
            lines.append(
                f"  {icon} {name:<8s} {pp:>+6.2f}  "
                f"{d['high_accuracy']*100:>8.1f}%  {d['low_accuracy']*100:>8.1f}%  "
                f"{d['high_avg_return']*100:>+7.1f}%  {d['low_avg_return']*100:>+7.1f}%"
            )

    # 建议
    lines += ["", f"  {thin}", "  💡 建议", f"  {thin}"]

    if buy_best and buy_best != 18:
        lines.append(f"  BUY 阈值: 18 → {buy_best} (准确率 {buy_acc*100:.1f}%)")
    else:
        lines.append(f"  BUY 阈值: 18 维持不变")

    if red_best and red_best != 8:
        lines.append(f"  REDUCE 阈值: 8 → {red_best} (准确率 {red_acc*100:.1f}%)")
    else:
        lines.append(f"  REDUCE 阈值: 8 维持不变")

    # 维度权重建议
    strong_dims = [name for name, d in dims.items() if d["predictive_power"] > 0.1]
    weak_dims = [name for name, d in dims.items() if d["predictive_power"] < -0.05]
    if strong_dims:
        lines.append(f"  强预测维度(建议加权): {', '.join(strong_dims)}")
    if weak_dims:
        lines.append(f"  弱预测维度(建议降权): {', '.join(weak_dims)}")

    lines.append(f"\n{sep}")
    return "\n".join(lines)


def apply_thresholds(result: dict, dry_run: bool = True) -> None:
    """将推荐阈值写入 scorer.py。

    TODO: 实际修改 scorer.py 中的阈值常量。
    目前仅打印建议，需人工确认。
    """
    buy_t = result.get("best_buy_threshold")
    red_t = result.get("best_reduce_threshold")

    if buy_t or red_t:
        print("\n需要手动更新以下文件:")
        print(f"  ~/.hermes/yidai/src/analysis/scorer.py")
        if buy_t:
            print(f"  BUY 阈值: 当前18 → 推荐{buy_t}")
        if red_t:
            print(f"  REDUCE 阈值: 当前8 → 推荐{red_t}")
        if dry_run:
            print("  [dry-run] 使用 --apply 实际执行")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="信号阈值校准")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="DuckDB 路径")
    parser.add_argument("--window", type=int, default=None, help="时间窗口(天)")
    parser.add_argument("--apply", action="store_true", help="应用推荐阈值")
    args = parser.parse_args()

    result = calibrate(db_path=Path(args.db), window_days=args.window)
    report = format_report(result)
    print(report)

    if args.apply:
        apply_thresholds(result, dry_run=False)
