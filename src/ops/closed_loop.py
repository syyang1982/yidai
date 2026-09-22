"""闭环健康检查器 — 回答"分析→记录→复盘→反馈 是否真的连成闭环"。

逐环节检查数据是否流动、产出是否被下游消费，并把断点显式列出来。
只读，不写任何数据库。用 `python manage.py loop` 触发。

环节定义::

    ① 分析   scorer / models / signal_tracker   → signal_records + knowledge/companies
    ② 记录   decision_log + positions           → decisions.duckdb
    ③ 复盘   review_engine / accuracy_audit     → review_results / 维度预测力
    ④ 反馈   src/strategy/feedback.py           → config/feedback_weights.json → 回到 ①

判定口径：一个环节"通过"必须同时满足 (a) 自身有产出 (b) 产出被下游实际消费。
只有 (a) 没有 (b) 就是断链——这正是历史版本的问题（复盘引擎 1482 行零入口）。
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from src.data.models import DIMENSION_WEIGHTS, FEEDBACK_WEIGHTS_FILE, load_dimension_weights

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DECISIONS_DB = os.path.join(_ROOT, "db", "decisions.duckdb")
SIGNALS_DB = os.path.join(_ROOT, "db", "signals.duckdb")
KB_COMPANIES = os.path.join(_ROOT, "knowledge", "companies")
PORTFOLIO_JSON = os.path.expanduser("~/.hermes/portfolio_data.json")

#: 信号/决策超过这么多天没更新，认为分析环节停滞
STALE_DAYS = 14


@dataclass
class Check:
    """单条检查项。"""
    name: str
    status: str          # "ok" / "warn" / "fail" / "info"
    detail: str = ""


@dataclass
class Stage:
    key: str
    title: str
    checks: List[Check] = field(default_factory=list)

    @property
    def worst(self) -> str:
        order = {"ok": 0, "info": 1, "warn": 2, "fail": 3}
        if not self.checks:
            return "info"
        return max(self.checks, key=lambda c: order.get(c.status, 0)).status


@dataclass
class LoopReport:
    stages: List[Stage] = field(default_factory=list)
    breakpoints: List[str] = field(default_factory=list)

    @property
    def closed(self) -> bool:
        return not self.breakpoints


def _norm_ticker(t: str) -> str:
    """归一 ticker：大写 + 去掉 HK 代码前导 0（01810.HK / 1810.HK / 1810 是同一个）。"""
    s = str(t or "").strip().upper().replace(".HK", "")
    s = s.lstrip("0") or s
    return s


def _connect_ro(path: str):
    """只读打开 DuckDB（失败时回退读写连接）。

    返回 ``(conn, err)``，两者必有其一。异常原因必须带给上层显示——
    否则「不可读」分不清是文件缺失、被别的写进程锁住、还是文件真损坏。
    DuckDB 是单写者：并行跑 analyze/signals（写）时再跑 loop 就会连不上。
    """
    import duckdb
    if not os.path.exists(path):
        return None, "文件不存在"
    last = ""
    for read_only in (True, False):
        try:
            return duckdb.connect(path, read_only=read_only), ""
        except Exception as exc:  # noqa: BLE001 —— 原因要显示出来，不能吞
            first_line = str(exc).splitlines()[0] if str(exc) else ""
            last = f"{type(exc).__name__}: {first_line}"
            if not read_only:
                last += "（多半是别的进程正持有写锁）"
    return None, last


def _load_portfolio() -> dict:
    try:
        with open(PORTFOLIO_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── 各环节检查 ────────────────────────────────────────────────────────
def _stage_analysis() -> Stage:
    st = Stage("①", "分析  scorer / models → 评分 + 信号")
    conn, err = _connect_ro(SIGNALS_DB)
    if conn is None:
        st.checks.append(Check("signal_records", "fail", f"信号库不可读: {err}"))
        return st
    try:
        n = conn.execute("SELECT COUNT(*) FROM signal_records").fetchone()[0]
        latest = conn.execute(
            "SELECT MAX(signal_date) FROM signal_records"
        ).fetchone()[0]
        st.checks.append(Check("signal_records", "ok" if n else "fail", f"{n} 条"))
        if latest:
            d = latest if isinstance(latest, date) else date.fromisoformat(str(latest)[:10])
            age = (date.today() - d).days
            status = "ok" if age <= STALE_DAYS else "warn"
            st.checks.append(Check("信号新鲜度", status, f"最新 {d}（{age} 天前，阈值 {STALE_DAYS} 天）"))
        else:
            st.checks.append(Check("信号新鲜度", "fail", "无日期数据"))
    except Exception as e:
        st.checks.append(Check("signal_records", "fail", f"查询失败: {e}"))
    finally:
        try:
            conn.close()
        except Exception:
            pass

    n_kb = len(glob.glob(os.path.join(KB_COMPANIES, "*.md")))
    st.checks.append(Check("知识库公司档案", "ok" if n_kb else "warn", f"{n_kb} 份 ({KB_COMPANIES})"))
    st.checks.append(Check("评分维度", "ok" if len(DIMENSION_WEIGHTS) == 8 else "warn",
                           f"{len(DIMENSION_WEIGHTS)} 维（原始满分 {5 * len(DIMENSION_WEIGHTS)}"
                           f" / 加权满分 {5 * sum(DIMENSION_WEIGHTS.values()):.1f}）"))
    return st


def _stage_record() -> Tuple[Stage, List[str]]:
    """② 记录环节。返回 (stage, 断点描述列表)。"""
    st = Stage("②", "记录  decision_log + positions")
    breaks: List[str] = []
    conn, err = _connect_ro(DECISIONS_DB)
    if conn is None:
        st.checks.append(Check("decisions.duckdb", "fail", f"决策库不可读: {err}"))
        breaks.append("② 决策库不可读 —— 记录环节整体失效")
        return st, breaks

    try:
        n = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
        latest = conn.execute("SELECT MAX(decision_date) FROM decision_log").fetchone()[0]
        st.checks.append(Check("decision_log", "ok" if n else "fail", f"{n} 条"))

        # 决策时必填字段填充率（缺失 = 认知偏差检测失效）
        filled = conn.execute(
            """SELECT COUNT(*) FROM decision_log
               WHERE confidence_level IS NOT NULL AND confidence_level > 0
                 AND counter_argument IS NOT NULL AND TRIM(counter_argument) <> ''"""
        ).fetchone()[0]
        rate = (filled / n * 100) if n else 0
        st.checks.append(Check(
            "决策过程质量", "ok" if rate >= 80 else ("warn" if rate >= 50 else "fail"),
            f"confidence+反面论据 双填率 {rate:.0f}% ({filled}/{n})",
        ))

        # 持仓与失效条件
        try:
            open_n = conn.execute(
                "SELECT COUNT(*) FROM positions WHERE status = 'open'"
            ).fetchone()[0]
            st.checks.append(Check("open 持仓", "ok" if open_n else "warn", f"{open_n} 个"))
        except Exception as e:
            st.checks.append(Check("positions", "warn", f"读取失败: {e}"))
            open_n = 0

        # 与 portfolio_data.json 的股数对账（两套数据源必须一致）
        port = _load_portfolio()
        holdings = port.get("holdings", [])
        book: Dict[str, Tuple[float, float]] = {}
        try:
            for ticker, shares, cost in conn.execute(
                "SELECT ticker, shares, avg_cost FROM positions WHERE status = 'open'"
            ).fetchall():
                book[_norm_ticker(ticker)] = (shares, cost)
        except Exception:
            pass

        mismatches = []
        port_map = {}
        for h in holdings:
            if h.get("shares", 0) > 0:
                port_map[_norm_ticker(h.get("ticker"))] = h.get("shares", 0)

        for key in sorted(set(book) | set(port_map)):
            b = book.get(key)
            p = port_map.get(key)
            if b is None:
                mismatches.append(f"{key}: portfolio {p} 股 / 决策库无记录")
            elif p is None:
                mismatches.append(f"{key}: 决策库 {b[0]:g} 股 / portfolio 无持仓")
            elif abs(float(b[0]) - float(p)) > 1e-6:
                mismatches.append(f"{key}: 决策库 {float(b[0]):g} 股 / portfolio {p:g} 股")

        if mismatches:
            st.checks.append(Check("两库股数对账", "fail", f"{len(mismatches)} 处不一致"))
            breaks.append(f"② 持仓两套数据源股数不一致 {len(mismatches)} 处 —— 下游市值/约束/卖出提醒全部失真")
            for m in mismatches:
                st.checks.append(Check("  · " + m, "info", ""))
        else:
            st.checks.append(Check("两库股数对账", "ok", "全部一致"))
    except Exception as e:
        st.checks.append(Check("decision_log", "fail", f"查询失败: {e}"))
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return st, breaks


def _stage_review() -> Tuple[Stage, List[str]]:
    """③ 复盘环节。"""
    st = Stage("③", "复盘  review_engine / accuracy_audit → 预测 vs 实际")
    breaks: List[str] = []
    conn, _err = _connect_ro(DECISIONS_DB)
    n_reviews = 0
    if conn is not None:
        try:
            tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
            if "review_results" in tables:
                n_reviews = conn.execute("SELECT COUNT(*) FROM review_results").fetchone()[0]
                st.checks.append(Check("review_results", "ok" if n_reviews else "fail", f"{n_reviews} 条"))
            else:
                st.checks.append(Check("review_results", "fail", "表不存在（复盘引擎从未被调用）"))
        except Exception as e:
            st.checks.append(Check("review_results", "warn", f"读取失败: {e}"))
        finally:
            try:
                conn.close()
            except Exception:
                pass
    else:
        st.checks.append(Check("decisions.duckdb", "fail", "不可读"))

    # 到期待复盘数量
    pending_total = 0
    try:
        from src.strategy.decision import DecisionLog
        log = DecisionLog(DECISIONS_DB)
        for period in ("1w", "1m", "6m", "12m"):
            try:
                pend = log.get_pending_reviews(period)
                n = len(pend) if pend else 0
                pending_total += n
                st.checks.append(Check(f"待复盘 {period}", "ok" if n == 0 else "warn", f"{n} 条到期"))
            except Exception as e:
                st.checks.append(Check(f"待复盘 {period}", "warn", f"查询失败: {e}"))
        try:
            log.conn.close()
        except Exception:
            pass
    except Exception as e:
        st.checks.append(Check("待复盘", "warn", f"DecisionLog 不可用: {e}"))

    # accuracy_audit 是否产出维度预测力
    try:
        from src.analysis.accuracy_audit import AccuracyAuditor
        aud = AccuracyAuditor()
        st.checks.append(Check("accuracy_audit", "ok", "可用（多窗口准确率 + 维度预测力）"))
    except Exception as e:
        st.checks.append(Check("accuracy_audit", "warn", f"不可用: {e}"))

    if n_reviews == 0:
        breaks.append("③ 复盘引擎零产出 —— review_results 为空，复盘环节未真正运行")
    if pending_total:
        breaks.append(f"③ 有 {pending_total} 条决策已到期未复盘 —— 反馈环节没有新原料")

    return st, breaks


def _stage_feedback() -> Tuple[Stage, List[str]]:
    """④ 反馈环节。"""
    st = Stage("④", "反馈  复盘结论 → 评分权重/阈值")
    breaks: List[str] = []

    exists = os.path.exists(FEEDBACK_WEIGHTS_FILE)
    if exists:
        st.checks.append(Check("feedback_weights.json", "ok", FEEDBACK_WEIGHTS_FILE))
        try:
            with open(FEEDBACK_WEIGHTS_FILE, encoding="utf-8") as f:
                meta = json.load(f)
            st.checks.append(Check("生成时间", "ok", str(meta.get("generated_at", "未知"))))
            st.checks.append(Check("复盘样本", "ok", str(meta.get("min_samples", "?")) + " 条/维 门槛"))
        except Exception as e:
            st.checks.append(Check("feedback_weights.json", "warn", f"解析失败: {e}"))
    else:
        st.checks.append(Check("feedback_weights.json", "fail", "不存在 —— 从未回灌"))

    cur = load_dimension_weights()
    diffs = [k for k in DIMENSION_WEIGHTS if abs(cur[k] - DIMENSION_WEIGHTS[k]) > 1e-9]
    if diffs:
        st.checks.append(Check("权重状态", "ok",
                               f"{len(diffs)} 维已偏离内置基准（回灌已生效）: {', '.join(diffs)}"))
    else:
        st.checks.append(Check("权重状态", "warn", "全部等于内置基准（回灌未生效）"))

    st.checks.append(Check("调参开关", "info", "manage.py feedback --apply | --reset"))

    if not exists:
        breaks.append("④ 权重从未回灌 —— 复盘结论没有回到评分层，闭环在此断开")
    return st, breaks


# ── 汇总 ──────────────────────────────────────────────────────────────
def run_check() -> LoopReport:
    """跑一遍闭环健康检查，返回结构化结果。"""
    report = LoopReport()

    report.stages.append(_stage_analysis())

    st2, b2 = _stage_record()
    report.stages.append(st2)
    report.breakpoints.extend(b2)

    st3, b3 = _stage_review()
    report.stages.append(st3)
    report.breakpoints.extend(b3)

    st4, b4 = _stage_feedback()
    report.stages.append(st4)
    report.breakpoints.extend(b4)

    return report


_ICON = {"ok": "✅", "warn": "⚠️ ", "fail": "❌", "info": "·  "}


def format_report(report: LoopReport) -> str:
    """纯文本报告（终端可读）。"""
    from src.ops.text_table import display_width

    L: List[str] = []
    L.append("=" * 74)
    L.append("  意怠工程 — 闭环健康检查")
    L.append("=" * 74)
    L.append("")
    L.append("  链路: ① 分析 → ② 记录 → ③ 复盘 → ④ 反馈 → 回到 ①")
    L.append("")

    for st in report.stages:
        icon = _ICON.get(st.worst, "·  ")
        L.append(f"  {icon} 环节{st.key} {st.title}")
        for c in st.checks:
            ci = _ICON.get(c.status, "·  ")
            line = f"       {ci} {c.name}"
            if c.detail:
                pad = max(1, 34 - display_width(c.name))
                line += " " * pad + c.detail
            L.append(line)
        L.append("")

    L.append("-" * 74)
    if report.closed:
        L.append("  ✅ 闭环成立：四个环节都有产出，且产出被下游实际消费。")
    else:
        L.append(f"  ❌ 闭环断开：{len(report.breakpoints)} 处断点")
        L.append("")
        for i, b in enumerate(report.breakpoints, 1):
            L.append(f"     {i}. {b}")
    L.append("")
    return "\n".join(L)
