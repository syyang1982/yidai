"""Weekly investment report generator for YiDAI.

Generates a self-contained markdown report covering all tracked companies,
their 7-dimension scores, grade/signal, week-over-week changes, and alerts.

The report is in Chinese and designed to be sent via cron job.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.data.store import YidaiStore


# ---------------------------------------------------------------------------
# Dimension display names (Chinese)
# ---------------------------------------------------------------------------

DIMENSION_NAMES = {
    "profitability_score": "盈利能力",
    "health_score": "财务健康",
    "cashflow_score": "现金流",
    "valuation_score": "估值",
    "growth_score": "成长性",
    "ownership_score": "股权结构",
    "strategy_score": "战略",
}

DIMENSION_KEYS = [
    "profitability_score",
    "health_score",
    "cashflow_score",
    "valuation_score",
    "growth_score",
    "ownership_score",
    "strategy_score",
]


# ---------------------------------------------------------------------------
# Utility formatters
# ---------------------------------------------------------------------------

def format_score_bar(score: int, max_score: int = 5) -> str:
    """Return a visual bar like '███░░' for score=3 out of max_score=5."""
    score = max(0, min(score or 0, max_score))
    filled = "█" * score
    empty = "░" * (max_score - score)
    return filled + empty


def format_signal_emoji(signal: str) -> str:
    """Return an emoji for the given signal string."""
    mapping = {
        "BUY": "🟢",
        "HOLD": "🟡",
        "WATCH": "🔵",
        "REDUCE": "🔴",
    }
    return mapping.get(signal, "⚪")


SIGNAL_CN = {
    "BUY": "买入",
    "HOLD": "持有",
    "WATCH": "观望",
    "REDUCE": "减仓",
}


def format_number(value: Optional[float], suffix: str = "") -> str:
    """Format a large number with Chinese units (亿/万) or just commas."""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1e8:
        return f"{sign}{abs_val / 1e8:.2f}亿{suffix}"
    if abs_val >= 1e4:
        return f"{sign}{abs_val / 1e4:.2f}万{suffix}"
    return f"{sign}{abs_val:,.2f}{suffix}"


def format_percent(value: Optional[float]) -> str:
    """Format a ratio as percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


# ---------------------------------------------------------------------------
# Core report generation
# ---------------------------------------------------------------------------

def _get_company_info(store: YidaiStore, ticker: str) -> dict:
    """Fetch company metadata from the store."""
    row = store.conn.execute(
        "SELECT ticker, name, market, currency, sector, notes "
        "FROM company WHERE ticker = ?",
        [ticker],
    ).fetchone()
    if row is None:
        return {"ticker": ticker, "name": ticker, "market": "", "currency": "",
                "sector": "", "notes": ""}
    columns = ["ticker", "name", "market", "currency", "sector", "notes"]
    return dict(zip(columns, row))


def _get_prev_score(store: YidaiStore, ticker: str, current_date: date) -> Optional[dict]:
    """Get the most recent score before current_date for a ticker."""
    columns = [
        "ticker", "date", "profitability_score", "health_score",
        "cashflow_score", "valuation_score", "growth_score",
        "ownership_score", "strategy_score", "total_score",
        "grade", "signal",
    ]
    row = store.conn.execute(
        "SELECT * FROM score_result "
        "WHERE ticker = ? AND date < ? "
        "ORDER BY date DESC LIMIT 1",
        [ticker, current_date],
    ).fetchone()
    if row is None:
        return None
    return dict(zip(columns, row))


def _render_company_section(
    company: dict,
    price_data: Optional[dict],
    latest_score: dict,
    prev_score: Optional[dict],
) -> str:
    """Render the markdown section for a single company."""
    ticker = company["ticker"]
    name = company.get("name") or ticker
    market = company.get("market", "")
    currency = company.get("currency", "")

    lines: List[str] = []
    lines.append(f"## {name} ({ticker})")
    lines.append("")
    if market:
        lines.append(f"**市场**: {market}  |  **货币**: {currency}")
    if company.get("sector"):
        lines.append(f"**行业**: {company['sector']}")
    lines.append("")

    # Price info
    if price_data:
        price = price_data.get("close_price")
        pe = price_data.get("pe_ratio")
        pb = price_data.get("pb_ratio")
        mc = price_data.get("market_cap")
        lines.append(f"**当前价格**: {format_number(price, currency)}")
        if pe:
            lines.append(f"**市盈率(P/E)**: {pe:.1f}x  |  **市净率(P/B)**: {pb:.1f}x" if pb else f"**市盈率(P/E)**: {pe:.1f}x")
        if mc:
            lines.append(f"**市值**: {format_number(mc)}")
    lines.append("")

    # Signal and grade
    signal = latest_score.get("signal", "WATCH")
    grade = latest_score.get("grade", "F")
    total = latest_score.get("total_score", 0)
    emoji = format_signal_emoji(signal)
    signal_cn = SIGNAL_CN.get(signal, signal)
    lines.append(f"### {emoji} 信号: {signal_cn}  |  评级: {grade}  |  总分: {total}/40")
    lines.append("")

    # 7-dimension scores with bars
    lines.append("### 七维评分")
    lines.append("")
    lines.append("| 维度 | 评分 | 可视化 |")
    lines.append("|------|------|--------|")
    for key in DIMENSION_KEYS:
        dim_name = DIMENSION_NAMES[key]
        score_val = latest_score.get(key, 0)
        bar = format_score_bar(score_val)
        lines.append(f"| {dim_name} | {score_val}/5 | {bar} |")
    lines.append("")

    # Week-over-week changes
    if prev_score:
        changes = []
        for key in DIMENSION_KEYS:
            curr = latest_score.get(key, 0)
            prev = prev_score.get(key, 0)
            diff = curr - prev
            if diff != 0:
                arrow = "↑" if diff > 0 else "↓"
                dim_name = DIMENSION_NAMES[key]
                changes.append(f"{dim_name} {prev}→{curr} ({arrow}{abs(diff)})")

        prev_total = prev_score.get("total_score", 0)
        total_diff = total - prev_total
        if total_diff != 0:
            arrow = "↑" if total_diff > 0 else "↓"
            changes.append(f"总分 {prev_total}→{total} ({arrow}{abs(total_diff)})")

        prev_signal = prev_score.get("signal", "")
        if prev_signal != signal:
            prev_emoji = format_signal_emoji(prev_signal)
            changes.append(
                f"信号变更: {prev_emoji}{SIGNAL_CN.get(prev_signal, prev_signal)}"
                f" → {emoji}{signal_cn}"
            )

        if changes:
            lines.append("### 本周变化")
            lines.append("")
            for c in changes:
                lines.append(f"- {c}")
            lines.append("")
    else:
        lines.append("*（首次评分，无历史对比）*")
        lines.append("")

    # Detailed metric breakdown
    lines.append("### 详细指标")
    lines.append("")
    _render_detail_section(lines, latest_score)
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _render_detail_section(lines: List[str], score: dict) -> None:
    """Render detailed metric info from the score details field."""
    details = score.get("details", [])
    if details:
        for detail in details:
            if detail.startswith("---"):
                # Section header
                lines.append(f"**{detail.strip('- ')}**")
            else:
                lines.append(f"- {detail}")
    else:
        # No details available; just show the raw scores
        for key in DIMENSION_KEYS:
            dim_name = DIMENSION_NAMES[key]
            score_val = score.get(key, 0)
            lines.append(f"- {dim_name}: {score_val}/5")


def _render_portfolio_overview(all_scores: List[dict]) -> str:
    """Render the portfolio-level overview section."""
    lines: List[str] = []
    lines.append("# 组合概览")
    lines.append("")

    # Grade distribution
    grade_counts: Dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    signal_counts: Dict[str, int] = {"BUY": 0, "HOLD": 0, "WATCH": 0, "REDUCE": 0}

    for s in all_scores:
        g = s.get("grade", "F")
        grade_counts[g] = grade_counts.get(g, 0) + 1
        sig = s.get("signal", "WATCH")
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    lines.append("### 评级分布")
    lines.append("")
    lines.append("| 评级 | 数量 | 分布 |")
    lines.append("|------|------|------|")
    total_companies = len(all_scores)
    for grade in ["A", "B", "C", "D", "F"]:
        count = grade_counts.get(grade, 0)
        bar_len = count * 4  # 4 chars per company in the bar
        bar = "█" * bar_len if count > 0 else ""
        pct = f"{count / total_companies * 100:.0f}%" if total_companies > 0 else "0%"
        lines.append(f"| {grade} | {count} | {bar} ({pct}) |")
    lines.append("")

    lines.append("### 信号分布")
    lines.append("")
    lines.append("| 信号 | 数量 |")
    lines.append("|------|------|")
    for sig in ["BUY", "HOLD", "WATCH", "REDUCE"]:
        emoji = format_signal_emoji(sig)
        cn = SIGNAL_CN.get(sig, sig)
        count = signal_counts.get(sig, 0)
        lines.append(f"| {emoji} {cn} | {count} |")
    lines.append("")

    # Summary stats
    avg_score = sum(s.get("total_score", 0) for s in all_scores) / total_companies if total_companies > 0 else 0
    lines.append(f"**跟踪公司总数**: {total_companies}")
    lines.append(f"**平均总分**: {avg_score:.1f}/40")
    lines.append("")

    return "\n".join(lines)


def _render_alerts(alerts: List[dict]) -> str:
    """Render the alerts section for signal changes."""
    if not alerts:
        return ""

    lines: List[str] = []
    lines.append("# ⚠️ 重要提醒")
    lines.append("")
    lines.append("以下公司本周发生了信号变更：")
    lines.append("")

    for alert in alerts:
        ticker = alert["ticker"]
        name = alert.get("name", ticker)
        old_signal = alert["old_signal"]
        new_signal = alert["new_signal"]
        old_emoji = format_signal_emoji(old_signal)
        new_emoji = format_signal_emoji(new_signal)
        old_cn = SIGNAL_CN.get(old_signal, old_signal)
        new_cn = SIGNAL_CN.get(new_signal, new_signal)

        severity = ""
        if new_signal == "REDUCE":
            severity = " ⚠️"
        elif new_signal == "BUY" and old_signal != "BUY":
            severity = " 🎯"

        lines.append(
            f"- **{name}** ({ticker}): "
            f"{old_emoji}{old_cn} → {new_emoji}{new_cn}{severity}"
        )
    lines.append("")
    return "\n".join(lines)


def generate_report(db_path: str, output_dir: str = "reports") -> str:
    """Generate a weekly investment report for all tracked companies.

    Reads all companies from DuckDB, scores each one, and produces a
    self-contained markdown report in Chinese.

    Args:
        db_path: Path to the DuckDB database file.
        output_dir: Directory to save the report (created if needed).

    Returns:
        Absolute path to the generated report file.
    """
    store = YidaiStore(db_path)
    today = date.today()

    tickers = store.get_all_tickers()

    all_scores: List[dict] = []
    alerts: List[dict] = []
    company_sections: List[str] = []

    for ticker in tickers:
        company = _get_company_info(store, ticker)
        price_data = store.get_latest_price(ticker)
        scores = store.get_scores(ticker)

        if not scores:
            # No score data for this company; skip or note it
            company_sections.append(
                f"## {company.get('name', ticker)} ({ticker})\n\n"
                f"*（暂无评分数据）*\n\n---\n"
            )
            continue

        latest_score = scores[-1]
        prev_score = _get_prev_score(store, ticker, latest_score["date"])

        all_scores.append(latest_score)

        # Check for signal changes
        if prev_score and prev_score.get("signal") != latest_score.get("signal"):
            alerts.append({
                "ticker": ticker,
                "name": company.get("name", ticker),
                "old_signal": prev_score["signal"],
                "new_signal": latest_score["signal"],
            })

        section = _render_company_section(company, price_data, latest_score, prev_score)
        company_sections.append(section)

    store.close()

    # --- Assemble the full report ---
    report_lines: List[str] = []

    # Header
    report_lines.append(f"# 意怠投资周报 — {today.strftime('%Y年%m月%d日')}")
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

    # Alerts (if any)
    alerts_text = _render_alerts(alerts)
    if alerts_text:
        report_lines.append(alerts_text)
        report_lines.append("---")
        report_lines.append("")

    # Portfolio overview
    if all_scores:
        overview_text = _render_portfolio_overview(all_scores)
        report_lines.append(overview_text)
        report_lines.append("---")
        report_lines.append("")

    # Individual company sections
    report_lines.append("# 个股分析")
    report_lines.append("")
    for section in company_sections:
        report_lines.append(section)

    # Footer
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("*本报告由意怠投资分析系统自动生成，仅供参考，不构成投资建议。*")
    report_lines.append("")

    report_content = "\n".join(report_lines)

    # Write to file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"weekly_{today.strftime('%Y-%m-%d')}.md"
    filepath = output_path / filename
    filepath.write_text(report_content, encoding="utf-8")

    return str(filepath.resolve())
