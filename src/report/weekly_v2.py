"""
增强版周报生成器 v2 — 整合知识库与信号追踪系统。

在 v1 基础上新增:
- 信号预警 (新信号 + 待回顾)
- 知识库投资论点 & 风险因素
- 知识库洞察 (经验教训 + 投资原则 + 预测准确度)
- 待办事项 (待回顾 / 恶化公司 / 评级边界)
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from src.data.store import YidaiStore
from src.report.weekly import (
    DIMENSION_KEYS,
    DIMENSION_NAMES,
    SIGNAL_CN,
    format_number,
    format_percent,
    format_score_bar,
    format_signal_emoji,
    _get_company_info,
    _get_prev_score,
    _render_company_section,
    _render_portfolio_overview,
)

from src.analysis.anomaly import detect_anomalies, AnomalyAlert
from src.data.fetcher import EastmoneyFetcher

# Optional imports — degrade gracefully if not available
try:
    from src.knowledge.base import KnowledgeBase
except ImportError:  # pragma: no cover
    KnowledgeBase = None  # type: ignore

try:
    from src.strategy.signal_tracker import SignalTracker
    from src.analysis.return_projection import project_returns, format_projection
except ImportError:  # pragma: no cover
    SignalTracker = None  # type: ignore


# ---------------------------------------------------------------------------
# Grade boundary helpers
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (29, "A"),
    (22, "B"),
    (15, "C"),
    (8, "D"),
    (0, "F"),
]

def _compute_grade_from_total(total: int) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if total >= threshold:
            return letter
    return "F"


def _next_grade_info(total: int) -> Optional[dict]:
    """Return info about the next grade boundary above *total*."""
    for threshold, letter in reversed(_GRADE_THRESHOLDS):
        if total < threshold:
            gap = threshold - total
            return {"next_grade": letter, "threshold": threshold, "gap": gap}
    return None


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_signal_alerts(
    new_signals: List[dict],
    pending_6m: List[dict],
    pending_12m: List[dict],
) -> str:
    """渲染信号预警区块。"""
    lines: List[str] = []
    lines.append("# 🔔 信号预警")
    lines.append("")

    has_content = False

    if new_signals:
        has_content = True
        lines.append("## 新信号 (最近一次报告后)")
        lines.append("")
        for sig in new_signals:
            emoji = format_signal_emoji(sig.get("signal_type", ""))
            cn = SIGNAL_CN.get(sig.get("signal_type", ""), sig.get("signal_type", ""))
            name = sig.get("company_name", sig.get("ticker", ""))
            ticker = sig.get("ticker", "")
            sig_date = sig.get("signal_date", "")
            lines.append(
                f"- {emoji} **{name}** ({ticker}) — {cn} "
                f"({sig_date})  评级: {sig.get('grade', 'N/A')}  "
                f"总分: {sig.get('total_score', 'N/A')}/35"
            )
        lines.append("")

    if pending_6m:
        has_content = True
        lines.append("## 待回顾 (6个月)")
        lines.append("")
        lines.append("| 股票 | 公司 | 信号日期 | 信号 | 总分 |")
        lines.append("|------|------|----------|------|------|")
        for sig in pending_6m:
            emoji = format_signal_emoji(sig.get("signal_type", ""))
            cn = SIGNAL_CN.get(sig.get("signal_type", ""), sig.get("signal_type", ""))
            lines.append(
                f"| {sig.get('ticker', '')} "
                f"| {sig.get('company_name', '')} "
                f"| {sig.get('signal_date', '')} "
                f"| {emoji}{cn} "
                f"| {sig.get('total_score', '')}/35 |"
            )
        lines.append("")

    if pending_12m:
        has_content = True
        lines.append("## 待回顾 (12个月)")
        lines.append("")
        lines.append("| 股票 | 公司 | 信号日期 | 信号 | 总分 |")
        lines.append("|------|------|----------|------|------|")
        for sig in pending_12m:
            emoji = format_signal_emoji(sig.get("signal_type", ""))
            cn = SIGNAL_CN.get(sig.get("signal_type", ""), sig.get("signal_type", ""))
            lines.append(
                f"| {sig.get('ticker', '')} "
                f"| {sig.get('company_name', '')} "
                f"| {sig.get('signal_date', '')} "
                f"| {emoji}{cn} "
                f"| {sig.get('total_score', '')}/35 |"
            )
        lines.append("")

    if not has_content:
        lines.append("*本周无新信号，无需回顾。*")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _render_company_kb_section(
    ticker: str,
    kb: Optional[object],
    all_lessons: List[dict],
) -> str:
    """为单个公司渲染知识库相关区块（论点 + 风险 + 经验）。"""
    if kb is None:
        return ""

    lines: List[str] = []
    has_content = False

    try:
        profile = kb.get_company_profile(ticker)
    except (FileNotFoundError, Exception):
        return ""

    # 投资论点
    thesis = profile.get("thesis", "").strip()
    if thesis and thesis != "待填写":
        has_content = True
        lines.append("#### 💡 投资论点")
        lines.append("")
        lines.append(thesis)
        lines.append("")

    # 风险因素
    risks = profile.get("risks", [])
    if risks:
        has_content = True
        lines.append("#### ⚠️ 风险因素")
        lines.append("")
        for risk in risks:
            lines.append(f"- {risk}")
        lines.append("")

    # 相关经验教训
    related_lessons = [
        l for l in all_lessons
        if l.get("source", "").upper() == ticker.upper()
    ]
    if related_lessons:
        has_content = True
        lines.append("#### 📖 相关经验")
        lines.append("")
        for l in related_lessons[-3:]:  # last 3
            lines.append(f"- [{l.get('date', '')}] {l.get('content', '')}")
        lines.append("")

    return "\n".join(lines) if has_content else ""


def _render_kb_insights(
    kb: Optional[object],
    signal_tracker: Optional[object],
) -> str:
    """渲染知识库洞察区块。"""
    lines: List[str] = []
    lines.append("# 📚 知识库洞察")
    lines.append("")

    has_content = False

    # 经验教训 (最近 5 条)
    if kb is not None:
        try:
            lessons = kb.get_lessons()
            if lessons:
                has_content = True
                lines.append("## 最近经验教训")
                lines.append("")
                for lesson in lessons[-5:]:
                    src = f" [{lesson.get('source', '')}]" if lesson.get("source") else ""
                    cat = f" ({lesson.get('category', '')})" if lesson.get("category") else ""
                    lines.append(
                        f"- **{lesson.get('date', '')}**{cat}{src}: "
                        f"{lesson.get('content', '')}"
                    )
                lines.append("")

            principles = kb.get_principles()
            if principles:
                has_content = True
                lines.append("## 投资原则")
                lines.append("")
                for p in principles[-5:]:
                    lines.append(
                        f"- **{p.get('date', '')}**: {p.get('principle', '')}"
                    )
                lines.append("")
        except Exception:
            pass

    # 预测准确度
    if signal_tracker is not None:
        try:
            stats = signal_tracker.get_accuracy_stats()
            total = stats.get("total_signals", 0)
            if total > 0:
                has_content = True
                lines.append("## 预测准确度统计")
                lines.append("")
                lines.append(f"- 已完成信号: {total} 条")
                lines.append(f"- 价格准确率: {stats.get('price_accuracy', 0) * 100:.1f}%")
                lines.append(f"- 评分准确率: {stats.get('score_accuracy', 0) * 100:.1f}%")
                lines.append(f"- 方向准确率: {stats.get('direction_accuracy', 0) * 100:.1f}%")
                lines.append(f"- 平均置信度: {stats.get('avg_confidence', 0):.1f}/5")
                lines.append("")
        except Exception:
            pass

    if not has_content:
        lines.append("*知识库暂无数据。*")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _render_action_items(
    pending_count: int,
    deteriorating: List[dict],
    near_boundary: List[dict],
) -> str:
    """渲染待办事项区块。"""
    lines: List[str] = []
    lines.append("# 📋 待办事项")
    lines.append("")

    has_content = False

    if pending_count > 0:
        has_content = True
        lines.append(f"- ⏳ **待回顾信号**: {pending_count} 条")
        lines.append("")

    if deteriorating:
        has_content = True
        lines.append("- 📉 **评分恶化的公司**:")
        for d in deteriorating:
            name = d.get("name", d.get("ticker", ""))
            ticker = d.get("ticker", "")
            prev_total = d.get("prev_total", 0)
            curr_total = d.get("curr_total", 0)
            lines.append(f"  - {name} ({ticker}): {prev_total}→{curr_total} (↓{prev_total - curr_total})")
        lines.append("")

    if near_boundary:
        has_content = True
        lines.append("- 🎯 **接近评级边界的公司**:")
        for nb in near_boundary:
            name = nb.get("name", nb.get("ticker", ""))
            ticker = nb.get("ticker", "")
            total = nb.get("total", 0)
            info = nb.get("next_grade_info", {})
            gap = info.get("gap", 0)
            next_g = info.get("next_grade", "")
            threshold = info.get("threshold", 0)
            lines.append(
                f"  - {name} ({ticker}): {total}/35 → 距 {next_g} 仅差 {gap} 分 (需 {threshold})"
            )
        lines.append("")

    if not has_content:
        lines.append("*暂无待办事项。*")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Anomaly alerts renderer
# ---------------------------------------------------------------------------

def _render_anomaly_alerts(all_alerts: List[AnomalyAlert]) -> str:
    """渲染异常预警区块，按严重程度分组（HIGH 优先，MEDIUM 其次）。

    Args:
        all_alerts: 所有公司的异常预警列表

    Returns:
        Markdown 格式的异常预警区块，如果没有预警则返回空字符串
    """
    if not all_alerts:
        return ""

    lines: List[str] = []
    lines.append("# ⚠️ 财务异常预警")
    lines.append("")

    # Group by severity: HIGH first, then MEDIUM
    high_alerts = [a for a in all_alerts if a.severity == "HIGH"]
    medium_alerts = [a for a in all_alerts if a.severity == "MEDIUM"]

    if high_alerts:
        lines.append("## 🔴 HIGH — 建议减仓")
        lines.append("")
        for a in high_alerts:
            name = a.company_name or a.ticker
            lines.append(f"### {name} ({a.ticker})")
            lines.append("")
            lines.append(f"- {a.emoji} **[{a.rule_id}] {a.rule_name}** ({a.severity})")
            lines.append(f"  - {a.detail}")
            if a.period:
                lines.append(f"  - 报告期: {a.period}")
            if a.metrics:
                kv = ", ".join(f"{k}={v}" for k, v in a.metrics.items())
                lines.append(f"  - 指标: {kv}")
            lines.append("")

    if medium_alerts:
        lines.append("## 🟡 MEDIUM — 标记跟踪")
        lines.append("")
        for a in medium_alerts:
            name = a.company_name or a.ticker
            lines.append(f"### {name} ({a.ticker})")
            lines.append("")
            lines.append(f"- {a.emoji} **[{a.rule_id}] {a.rule_name}** ({a.severity})")
            lines.append(f"  - {a.detail}")
            if a.period:
                lines.append(f"  - 报告期: {a.period}")
            if a.metrics:
                kv = ", ".join(f"{k}={v}" for k, v in a.metrics.items())
                lines.append(f"  - 指标: {kv}")
            lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report_v2(
    db_path: str,
    kb_dir: Optional[str] = None,
    signal_db_path: Optional[str] = None,
    output_dir: str = "reports",
) -> str:
    """Generate an enhanced weekly report integrating knowledge base and signal tracker.

    Args:
        db_path: Path to the DuckDB database (score data).
        kb_dir: Path to knowledge base directory. Defaults to ~/.hermes/yidai/knowledge/
        signal_db_path: Path to signal tracker DuckDB. Defaults to ~/.hermes/yidai/db/signals.duckdb
        output_dir: Directory to save the report.

    Returns:
        Absolute path to the generated report file.
    """
    home = os.path.expanduser("~")
    if kb_dir is None:
        kb_dir = os.path.join(home, ".hermes", "yidai", "knowledge")
    if signal_db_path is None:
        signal_db_path = os.path.join(home, ".hermes", "yidai", "db", "signals.duckdb")

    store = YidaiStore(db_path)
    today = date.today()

    # Initialize optional components
    kb = None
    if KnowledgeBase is not None and os.path.isdir(kb_dir):
        try:
            kb = KnowledgeBase(kb_dir)
        except Exception:
            pass

    signal_tracker = None
    if SignalTracker is not None:
        try:
            signal_tracker = SignalTracker(signal_db_path)
        except Exception:
            pass

    # Gather data
    tickers = store.get_all_tickers()
    all_scores: List[dict] = []
    alerts: List[dict] = []
    company_sections: List[str] = []

    # KB lessons cache
    all_lessons: List[dict] = []
    if kb is not None:
        try:
            all_lessons = kb.get_lessons()
        except Exception:
            pass

    # Signal data
    new_signals: List[dict] = []
    pending_6m: List[dict] = []
    pending_12m: List[dict] = []
    if signal_tracker is not None:
        try:
            new_signals = signal_tracker.get_signal_history()[-5:]  # last 5 as "new"
            pending_6m = signal_tracker.get_pending_reviews("6m")
            pending_12m = signal_tracker.get_pending_reviews("12m")
        except Exception:
            pass

    # Process each company
    deteriorating: List[dict] = []
    near_boundary: List[dict] = []

    for ticker in tickers:
        company = _get_company_info(store, ticker)
        price_data = store.get_latest_price(ticker)
        scores = store.get_scores(ticker)

        if not scores:
            company_sections.append(
                f"## {company.get('name', ticker)} ({ticker})\n\n"
                f"*（暂无评分数据）*\n\n---\n"
            )
            continue

        latest_score = scores[-1]
        prev_score = _get_prev_score(store, ticker, latest_score["date"])

        all_scores.append(latest_score)

        # Detect signal changes
        if prev_score and prev_score.get("signal") != latest_score.get("signal"):
            alerts.append({
                "ticker": ticker,
                "name": company.get("name", ticker),
                "old_signal": prev_score["signal"],
                "new_signal": latest_score["signal"],
            })

        # Detect deteriorating scores
        if prev_score:
            prev_total = prev_score.get("total_score", 0)
            curr_total = latest_score.get("total_score", 0)
            if curr_total < prev_total:
                deteriorating.append({
                    "ticker": ticker,
                    "name": company.get("name", ticker),
                    "prev_total": prev_total,
                    "curr_total": curr_total,
                })

        # Detect near grade boundary
        total = latest_score.get("total_score", 0)
        next_info = _next_grade_info(total)
        if next_info and next_info["gap"] <= 3:
            near_boundary.append({
                "ticker": ticker,
                "name": company.get("name", ticker),
                "total": total,
                "next_grade_info": next_info,
            })

        # Render company section (reuse v1 renderer)
        section = _render_company_section(company, price_data, latest_score, prev_score)

        # Append return projection for BUY/REDUCE signals
        signal_type = latest_score.get("signal", "")
        if signal_type in ("BUY", "REDUCE"):
            try:
                proj = project_returns({
                    "current_price": price_data.get("close_price"),
                    "pe_ratio": price_data.get("pe_ratio"),
                    "pe_history_percentile": None,
                    "revenue_growth": None,
                    "net_margin": None,
                    "roe": None,
                    "dividend_yield": 0,
                    "signal": signal_type,
                })
                # Try to get better data from scores
                if latest_score:
                    proj = project_returns({
                        "current_price": price_data.get("close_price"),
                        "pe_ratio": price_data.get("pe_ratio"),
                        "pe_history_percentile": None,
                        "revenue_growth": None,
                        "net_margin": None,
                        "roe": None,
                        "dividend_yield": 0,
                        "signal": signal_type,
                    })
                proj_text = format_projection(proj, signal_type)
                section = section.rstrip()
                if section.endswith("---"):
                    section = section[:-3].rstrip() + "\n\n" + proj_text + "\n\n---\n"
                else:
                    section += "\n" + proj_text
            except Exception:
                pass  # Skip projection if data insufficient

        # Append KB enrichment
        kb_section = _render_company_kb_section(ticker, kb, all_lessons)
        if kb_section:
            # Insert before the final "---"
            if section.rstrip().endswith("---"):
                section = section.rstrip().rstrip("-").rstrip() + "\n\n" + kb_section + "\n---\n"
            else:
                section += "\n" + kb_section

        company_sections.append(section)

    # Anomaly detection — fetch multi-year financial data and run detection
    all_anomaly_alerts: List[AnomalyAlert] = []
    try:
        fetcher = EastmoneyFetcher()
        for ticker in tickers:
            try:
                company = _get_company_info(store, ticker)
                company_name = company.get("name", ticker)
                # Convert ticker to eastmoney code format
                east_ticker = ticker.replace(".HK", "").replace(".SZ", "").replace(".SH", "")
                all_fin = fetcher.fetch_financials(east_ticker, periods=10)
                annual = sorted(
                    [f for f in all_fin if f.get("period", "").endswith("12-31")],
                    key=lambda x: x.get("period", ""),
                )
                if len(annual) >= 2:
                    alerts_for_company = detect_anomalies(ticker, annual, company_name)
                    all_anomaly_alerts.extend(alerts_for_company)
            except Exception:
                continue  # Skip company if data unavailable
    except Exception:
        pass  # Fetcher init failed — skip anomaly detection entirely

    store.close()

    # Close signal tracker connection
    if signal_tracker is not None:
        try:
            signal_tracker.conn.close()
        except Exception:
            pass

    # --- Assemble the full report ---
    report_lines: List[str] = []

    # 1. Header
    report_lines.append(f"# 意怠投资增强周报 — {today.strftime('%Y年%m月%d日')}")
    report_lines.append("")
    report_lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append(f"**跟踪公司数**: {len(tickers)}")

    buy_count = sum(1 for s in all_scores if s.get("signal") == "BUY")
    hold_count = sum(1 for s in all_scores if s.get("signal") == "HOLD")
    watch_count = sum(1 for s in all_scores if s.get("signal") == "WATCH")
    reduce_count = sum(1 for s in all_scores if s.get("signal") == "REDUCE")
    report_lines.append(
        f"**信号汇总**: "
        f"{format_signal_emoji('BUY')} 买入 {buy_count} | "
        f"{format_signal_emoji('HOLD')} 持有 {hold_count} | "
        f"{format_signal_emoji('WATCH')} 观望 {watch_count} | "
        f"{format_signal_emoji('REDUCE')} 减仓 {reduce_count}"
    )
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # 2. Signal Alerts
    signal_alerts_text = _render_signal_alerts(new_signals, pending_6m, pending_12m)
    report_lines.append(signal_alerts_text)

    # Original v1 alerts (signal changes)
    if alerts:
        report_lines.append("# ⚠️ 信号变更提醒")
        report_lines.append("")
        for alert in alerts:
            old_emoji = format_signal_emoji(alert["old_signal"])
            new_emoji = format_signal_emoji(alert["new_signal"])
            old_cn = SIGNAL_CN.get(alert["old_signal"], alert["old_signal"])
            new_cn = SIGNAL_CN.get(alert["new_signal"], alert["new_signal"])
            report_lines.append(
                f"- **{alert['name']}** ({alert['ticker']}): "
                f"{old_emoji}{old_cn} → {new_emoji}{new_cn}"
            )
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")

    # 2.5 Anomaly alerts (only if there are any)
    anomaly_text = _render_anomaly_alerts(all_anomaly_alerts)
    if anomaly_text:
        report_lines.append(anomaly_text)

    # 3. Portfolio overview
    if all_scores:
        overview_text = _render_portfolio_overview(all_scores)
        report_lines.append(overview_text)
        report_lines.append("---")
        report_lines.append("")

    # 4. Per-company analysis
    report_lines.append("# 个股分析")
    report_lines.append("")
    for section in company_sections:
        report_lines.append(section)

    # 5. KB Insights
    kb_text = _render_kb_insights(kb, signal_tracker)
    report_lines.append(kb_text)

    # 6. Action items
    pending_total = len(pending_6m) + len(pending_12m)
    action_text = _render_action_items(pending_total, deteriorating, near_boundary)
    report_lines.append(action_text)

    # 7. Disclaimer
    report_lines.append("---")
    report_lines.append("")
    report_lines.append(
        "*本报告由意怠投资分析系统自动生成（增强版 v2），整合知识库与信号追踪数据，"
        "仅供参考，不构成投资建议。投资有风险，决策需谨慎。*"
    )
    report_lines.append("")

    report_content = "\n".join(report_lines)

    # Write to file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"weekly_v2_{today.strftime('%Y-%m-%d')}.md"
    filepath = output_path / filename
    filepath.write_text(report_content, encoding="utf-8")

    return str(filepath.resolve())
