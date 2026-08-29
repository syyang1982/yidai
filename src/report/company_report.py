"""
个股深度报告生成器 — 意怠工程 (Yidai)

为单家公司生成完整的投研分析报告，整合：
- 七维评分详情
- 财务异常预警
- 决策历史
- 信号历史
- 知识库（论点、风险、经验）
- 回报预期
- 行业对比
"""

from __future__ import annotations

import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional


def generate_company_report(
    ticker: str,
    db_path: str = None,
    kb_dir: str = None,
    signal_db_path: str = None,
    output_dir: str = "reports",
) -> str:
    """为单家公司生成深度分析报告。

    Args:
        ticker: 股票代码 (如 01810.HK)
        db_path: DuckDB 评分数据库路径
        kb_dir: 知识库目录
        signal_db_path: 信号/决策数据库路径
        output_dir: 报告输出目录

    Returns:
        生成的报告文件绝对路径
    """
    home = os.path.expanduser("~")
    if db_path is None:
        db_path = os.path.join(home, ".hermes", "yidai", "db", "yidai.duckdb")
    if kb_dir is None:
        kb_dir = os.path.join(home, ".hermes", "yidai", "knowledge")
    if signal_db_path is None:
        signal_db_path = os.path.join(home, ".hermes", "yidai", "db", "signals.duckdb")

    # Resolve company info
    company_name = ticker
    market = "HK" if ".HK" in ticker else ("SH" if ".SH" in ticker else ("SZ" if ".SZ" in ticker else "US"))
    sector = ""

    # Knowledge Base
    kb = None
    profile = {}
    try:
        from src.knowledge.base import KnowledgeBase
        if os.path.isdir(kb_dir):
            kb = KnowledgeBase(kb_dir)
            profile = kb.get_company_profile(ticker)
            company_name = profile.get("name", ticker)
            sector = profile.get("sector", "")
    except Exception:
        pass

    # Fetch financial data
    fetcher = None
    annual = []
    price_data = {}
    try:
        from src.data.fetcher import EastmoneyFetcher
        fetcher = EastmoneyFetcher()
        east_ticker = ticker.replace(".HK", "").replace(".SZ", "").replace(".SH", "")
        all_fin = fetcher.fetch_financials(east_ticker, periods=10)
        annual = sorted(
            [f for f in all_fin if f.get("period", "").endswith("12-31")],
            key=lambda x: x.get("period", ""),
        )
        price_data = fetcher.fetch_price(east_ticker)
    except Exception:
        pass

    # Scoring
    score_result = None
    all_details = []
    if annual and len(annual) >= 2:
        try:
            from src.analysis.scorer import score_all
            from src.data.models import _compute_grade, _compute_signal

            latest = annual[-1]
            prev = annual[-2]
            prev_prev = annual[-3] if len(annual) >= 3 else None

            # Get qualitative scores
            kb_scores = profile.get("scores", {})
            ownership = kb_scores.get("股东", 3)
            strategy = kb_scores.get("战略", 3)
            if isinstance(ownership, dict): ownership = ownership.get("score", 3)
            if isinstance(strategy, dict): strategy = strategy.get("score", 3)

            # Build growth data (multi-year)
            growth_rates = []
            for i in range(1, len(annual)):
                r_curr = annual[i].get("revenue", 0) or 0
                r_prev = annual[i-1].get("revenue", 0) or 0
                if r_prev > 0:
                    growth_rates.append((r_curr - r_prev) / r_prev)

            # Try peer PE
            peer_median_pe = None
            try:
                if fetcher:
                    peer_data = fetcher.fetch_peer_pe(ticker)
                    if peer_data:
                        peer_median_pe = peer_data.get("peer_median_pe")
            except Exception:
                pass

            score_result = score_all(
                financial_data=latest,
                price_data=price_data,
                qualitative_scores={"ownership": ownership, "strategy": strategy},
                prev_financial_data=prev,
                all_annual_data=annual,
                peer_median_pe=peer_median_pe,
            )
        except Exception:
            pass

    # Anomaly detection
    anomaly_alerts = []
    if annual and len(annual) >= 2:
        try:
            from src.analysis.anomaly import detect_anomalies
            anomaly_alerts = detect_anomalies(ticker, annual, company_name)
        except Exception:
            pass

    # Decision history
    decisions = []
    try:
        from src.strategy.decision import DecisionLog
        if os.path.exists(signal_db_path):
            dl = DecisionLog(signal_db_path)
            decisions = dl.list_decisions(ticker=ticker, limit=20)
    except Exception:
        pass

    # Signal history
    signals = []
    try:
        from src.strategy.signal_tracker import SignalTracker
        if os.path.exists(signal_db_path):
            st = SignalTracker(signal_db_path)
            signals = st.get_signal_history(ticker=ticker)
    except Exception:
        pass

    # Return projection
    projection = None
    if price_data and score_result:
        try:
            from src.analysis.return_projection import project_returns, format_projection
            latest = annual[-1] if annual else {}
            projection = project_returns({
                "current_price": price_data.get("close_price"),
                "pe_ratio": price_data.get("pe_ratio"),
                "pe_history_percentile": None,
                "revenue_growth": None,
                "net_margin": None,
                "roe": None,
                "dividend_yield": 0,
                "signal": score_result.signal if hasattr(score_result, "signal") else "HOLD",
            })
        except Exception:
            pass

    # ── Assemble report ──
    lines = []
    today = date.today().strftime("%Y年%m月%d日")

    # Header
    lines.append(f"# {company_name} ({ticker}) 深度分析报告")
    lines.append("")
    lines.append(f"**生成日期**: {today}")
    lines.append(f"**市场**: {market}")
    if sector:
        lines.append(f"**行业**: {sector}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. 公司概况
    lines.append("## 一、公司概况")
    lines.append("")
    thesis = profile.get("thesis", "").strip()
    if thesis and thesis != "待填写":
        lines.append(f"**投资论点**: {thesis}")
        lines.append("")
    notes = profile.get("notes", "").strip()
    if notes:
        lines.append(f"**备注**: {notes}")
        lines.append("")
    if not thesis and not notes:
        lines.append("*暂无公司概况信息。*")
        lines.append("")

    # 2. 七维评分详情
    lines.append("---")
    lines.append("")
    lines.append("## 二、七维评分")
    lines.append("")

    if score_result:
        dim_names = ["盈利", "健康", "现金流", "估值", "成长", "股东", "战略"]
        dim_keys = [
            "profitability_score", "health_score", "cashflow_score",
            "valuation_score", "growth_score", "ownership_score", "strategy_score",
        ]

        total = score_result.get("total_score", 0)
        grade = score_result.get("grade", "F")
        signal = score_result.get("signal", "WATCH")
        lines.append(f"**总分**: {total}/40 (**{grade}**) 信号: **{signal}**")
        lines.append("")
        lines.append("| 维度 | 分数 | 状态 |")
        lines.append("|------|------|------|")
        for name, key in zip(dim_names, dim_keys):
            score = score_result.get(key, 0)
            bar = "█" * score + "░" * (5 - score)
            status = "✅" if score >= 4 else ("⚠️" if score >= 2 else "❌")
            lines.append(f"| {name} | {bar} {score}/5 | {status} |")
        lines.append("")

        # Detailed checks
        details = score_result.get("details", [])
        if details:
            lines.append("### 评分细节")
            lines.append("")
            for detail in details:
                lines.append(f"- {detail}")
            lines.append("")
    else:
        lines.append("*数据不足，无法计算评分。*")
        lines.append("")

    # 3. 财务异常预警
    lines.append("---")
    lines.append("")
    lines.append("## 三、财务异常预警")
    lines.append("")

    if anomaly_alerts:
        for alert in anomaly_alerts:
            lines.append(f"{alert.emoji} **[{alert.rule_id}] {alert.rule_name}** ({alert.severity})")
            lines.append(f"  - {alert.detail}")
            if alert.period:
                lines.append(f"  - 报告期: {alert.period}")
            if alert.metrics:
                kv = ", ".join(f"{k}={v}" for k, v in alert.metrics.items())
                lines.append(f"  - 指标: {kv}")
            lines.append("")
    else:
        lines.append("🟢 未检测到异常信号。")
        lines.append("")

    # 4. 决策历史
    lines.append("---")
    lines.append("")
    lines.append("## 四、决策历史")
    lines.append("")

    if decisions:
        lines.append("| 日期 | 操作 | 股数 | 价格 | 理由 | 评分 | 收益 |")
        lines.append("|------|------|------|------|------|------|------|")
        for d in decisions:
            ret_str = ""
            if d.actual_return_pct != 0:
                ret_str = f"{d.actual_return_pct:+.1f}%"
            lines.append(
                f"| {d.decision_date} | {d.action} | {d.shares:,} | "
                f"{d.price:.2f} | {d.reason[:20]} | "
                f"{d.total_score}/{d.grade} | {ret_str} |"
            )
        lines.append("")
    else:
        lines.append("*暂无决策记录。*")
        lines.append("")

    # 5. 信号历史
    lines.append("---")
    lines.append("")
    lines.append("## 五、信号历史")
    lines.append("")

    if signals:
        lines.append("| 日期 | 信号 | 总分 | 等级 | 来源 |")
        lines.append("|------|------|------|------|------|")
        for s in signals[-10:]:  # last 10
            lines.append(
                f"| {s.get('signal_date', '')} | {s.get('signal_type', '')} | "
                f"{s.get('total_score', '')}/40 | {s.get('grade', '')} | "
                f"{s.get('signal_source', '')} |"
            )
        lines.append("")
    else:
        lines.append("*暂无信号记录。*")
        lines.append("")

    # 6. 投资论点与风险
    lines.append("---")
    lines.append("")
    lines.append("## 六、投资论点与风险")
    lines.append("")

    risks = profile.get("risks", [])
    if risks:
        lines.append("### ⚠️ 风险因素")
        lines.append("")
        for risk in risks:
            lines.append(f"- {risk}")
        lines.append("")

    # Related lessons
    if kb:
        try:
            lessons = kb.get_lessons()
            related = [l for l in lessons if l.get("source", "").upper() == ticker.upper()]
            if related:
                lines.append("### 📖 相关经验")
                lines.append("")
                for l in related[-5:]:
                    lines.append(f"- **{l.get('date', '')}**: {l.get('content', '')}")
                lines.append("")
        except Exception:
            pass

    if not risks and not (kb and any(l.get("source", "").upper() == ticker.upper()
                                      for l in (kb.get_lessons() or []))):
        lines.append("*暂无论点、风险或经验记录。*")
        lines.append("")

    # 7. 回报预期
    lines.append("---")
    lines.append("")
    lines.append("## 七、回报预期")
    lines.append("")

    if projection:
        try:
            from src.analysis.return_projection import format_projection
            signal = score_result.get("signal", "HOLD") if score_result else "HOLD"
            proj_text = format_projection(projection, signal)
            lines.append(proj_text)
        except Exception:
            lines.append("*回报预期格式化失败。*")
    else:
        lines.append("*数据不足，无法生成回报预期。*")
    lines.append("")

    # 8. 行业对比
    lines.append("---")
    lines.append("")
    lines.append("## 八、行业对比")
    lines.append("")

    peer_median_pe = None
    try:
        if fetcher:
            peer_data = fetcher.fetch_peer_pe(ticker)
            if peer_data:
                peer_median_pe = peer_data.get("peer_median_pe")
                peer_group = peer_data.get("peer_group", "")
                peer_pes = peer_data.get("peer_pes", [])
                my_pe = price_data.get("pe_ratio")

                lines.append(f"**行业组**: {peer_group}")
                lines.append("")
                if my_pe:
                    lines.append(f"**本公司 PE**: {my_pe:.1f}")
                lines.append(f"**行业中位数 PE**: {peer_median_pe:.1f}")
                lines.append("")

                if peer_pes:
                    lines.append("| 公司代码 | PE |")
                    lines.append("|----------|-----|")
                    for code, pe in sorted(peer_pes, key=lambda x: x[1] or 0):
                        marker = " ← 本公司" if code == east_ticker else ""
                        pe_str = f"{pe:.1f}" if pe else "N/A"
                        lines.append(f"| {code} | {pe_str}{marker} |")
                    lines.append("")
    except Exception:
        pass

    if peer_median_pe is None:
        lines.append("*暂无行业对比数据。*")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        "*本报告由意怠投资分析系统自动生成，仅供参考，不构成投资建议。投资有风险，决策需谨慎。*"
    )
    lines.append("")

    report_content = "\n".join(lines)

    # Write to file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_ticker = ticker.replace(".", "_")
    filename = f"company_{safe_ticker}_{date.today().strftime('%Y-%m-%d')}.md"
    filepath = output_path / filename
    filepath.write_text(report_content, encoding="utf-8")

    return str(filepath.resolve())
