"""Insider activity detection module (Check 6 of Valuation).

Detects signals that insiders may consider the company overvalued:
  1. 大股东/高管减持 — major shareholder or executive selling
  2. 增发/配股 — share issuance / rights offering (dilution)

These signals are advisory warnings — they do NOT directly reduce the
valuation score but are surfaced as ⚠️ alerts in the analysis output.

Severity levels:
  - high:   大股东大幅减持 (>1% of shares), or 定向增发 (private placement)
  - medium: 高管减持, 配股 (rights issue)
  - low:    小额减持, 公开增发 (public offering)

The check returns a dict with:
  - has_warning: bool — True if any insider activity detected
  - severity: 'none' / 'low' / 'medium' / 'high'
  - warnings: list of human-readable warning strings (Chinese)
  - details: list of raw event dicts for drill-down
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

def _classify_reduction(holder_type: str, shares_pct: Optional[float],
                        amount: Optional[float]) -> str:
    """Classify severity of a share reduction event.

    Args:
        holder_type: 'major' / 'executive' / 'institutional' / etc.
        shares_pct: percentage of total shares reduced (e.g. 1.5 means 1.5%)
        amount: absolute number of shares reduced

    Returns:
        'high' / 'medium' / 'low'
    """
    if holder_type in ("major", "控股股东", "实际控制人"):
        # Major shareholder selling is the strongest bearish signal
        if shares_pct is not None and shares_pct >= 1.0:
            return "high"
        return "medium"

    if holder_type in ("executive", "高管", "董事", "监事"):
        return "medium"

    # Institutional or minor shareholders
    if shares_pct is not None and shares_pct >= 0.5:
        return "medium"
    return "low"


def _classify_issuance(issuance_type: str, amount: Optional[float]) -> str:
    """Classify severity of a share issuance event.

    Args:
        issuance_type: '定增' / '配股' / '公开增发' / '可转债' / etc.
        amount: amount raised (in CNY/HKD)

    Returns:
        'high' / 'medium' / 'low'
    """
    # Private placement (定向增发) is most bearish — insiders selling at discount
    if issuance_type in ("定增", "定向增发", "非公开发行"):
        return "high"

    # Rights issue or convertible bonds — dilutive but less negative
    if issuance_type in ("配股", "可转债"):
        return "medium"

    # Public offering
    return "low"


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def check_insider_activity(events: list[dict],
                           lookback_days: int = 365) -> dict:
    """Analyze insider activity events for valuation warnings.

    Args:
        events: list of event dicts, each with at minimum:
            - event_type: 'reduction' / 'issuance' / 'buyback' / etc.
            - date: 'YYYY-MM-DD' or similar parseable date
            - holder_type (for reductions): 'major' / 'executive' / etc.
            - holder_name: name of the person/entity
            - shares_traded: number of shares (negative for selling)
            - shares_pct: percentage of total shares
            - amount: transaction amount
            - issuance_type (for issuances): '定增' / '配股' / etc.
        lookback_days: only consider events within this many days (default 365)

    Returns:
        dict with keys: has_warning, severity, warnings, details
    """
    if not events:
        return {
            "has_warning": False,
            "severity": "none",
            "warnings": [],
            "details": [],
        }

    cutoff = datetime.now() - timedelta(days=lookback_days)
    reductions: list[dict] = []
    issuances: list[dict] = []
    buybacks: list[dict] = []

    for evt in events:
        # Parse date
        evt_date_str = evt.get("date", "")
        try:
            evt_date = datetime.strptime(evt_date_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue  # skip events with unparseable dates

        if evt_date < cutoff:
            continue  # too old

        evt_type = evt.get("event_type", "")
        if evt_type in ("reduction", "减持"):
            reductions.append(evt)
        elif evt_type in ("issuance", "增发"):
            issuances.append(evt)
        elif evt_type in ("buyback", "回购"):
            buybacks.append(evt)

    warnings: list[str] = []
    details: list[dict] = []
    max_severity = "none"
    severity_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}

    # --- Process reductions ---
    for evt in reductions:
        holder_type = evt.get("holder_type", "unknown")
        holder_name = evt.get("holder_name", "未知")
        shares_pct = evt.get("shares_pct")
        shares_traded = evt.get("shares_traded")
        amount = evt.get("amount")

        sev = _classify_reduction(holder_type, shares_pct, amount)
        if severity_rank[sev] > severity_rank[max_severity]:
            max_severity = sev

        pct_str = f"{shares_pct:.2f}%" if shares_pct is not None else ""
        amt_str = f"{amount/1e8:.2f}亿" if amount and amount > 0 else ""

        if sev == "high":
            warnings.append(
                f"⚠️ 重大减持: {holder_name}({holder_type})减持 {pct_str} "
                f"{'金额'+amt_str if amt_str else ''} — 可能信号: 估值短期见顶"
            )
        elif sev == "medium":
            warnings.append(
                f"⚠️ 减持: {holder_name}({holder_type})减持 "
                f"{pct_str} {'金额'+amt_str if amt_str else ''}"
            )
        else:
            warnings.append(
                f"ℹ️ 小额减持: {holder_name}"
            )

        details.append({
            "type": "reduction",
            "severity": sev,
            **evt,
        })

    # --- Process issuances ---
    for evt in issuances:
        issuance_type = evt.get("issuance_type", "增发")
        amount = evt.get("amount")
        shares_pct = evt.get("shares_pct")

        sev = _classify_issuance(issuance_type, amount)
        if severity_rank[sev] > severity_rank[max_severity]:
            max_severity = sev

        amt_str = f"{amount/1e8:.2f}亿" if amount and amount > 0 else ""
        pct_str = f"{shares_pct:.2f}%" if shares_pct is not None else ""

        if sev == "high":
            warnings.append(
                f"⚠️ 定向增发: {issuance_type} {'金额'+amt_str if amt_str else ''} "
                f"{'稀释'+pct_str if pct_str else ''} — 可能信号: 公司认为当前股价足够高"
            )
        elif sev == "medium":
            warnings.append(
                f"⚠️ 增发/配股: {issuance_type} {'金额'+amt_str if amt_str else ''}"
            )
        else:
            warnings.append(
                f"ℹ️ 增发: {issuance_type} {amt_str}"
            )

        details.append({
            "type": "issuance",
            "severity": sev,
            **evt,
        })

    # --- Buybacks are positive (counter-signal) ---
    for evt in buybacks:
        amount = evt.get("amount")
        amt_str = f"{amount/1e8:.2f}亿" if amount and amount > 0 else ""
        warnings.append(
            f"✅ 回购: {amt_str} — 正面信号 (管理层认为股价低估)"
        )
        details.append({
            "type": "buyback",
            "severity": "positive",
            **evt,
        })

    return {
        "has_warning": len(reductions) > 0 or len(issuances) > 0,
        "severity": max_severity,
        "warnings": warnings,
        "details": details,
        "summary": {
            "reductions": len(reductions),
            "issuances": len(issuances),
            "buybacks": len(buybacks),
        },
    }


# ---------------------------------------------------------------------------
# Format for display
# ---------------------------------------------------------------------------

def format_insider_warnings(result: dict) -> str:
    """Format insider activity check result for terminal display.

    Returns:
        Multi-line string with warnings, or empty string if no warnings.
    """
    if not result.get("has_warning") and not result.get("warnings"):
        return ""

    severity = result.get("severity", "none")
    emoji = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(severity, "⚪")

    lines = [f"  {emoji} 内部人行为信号 (severity: {severity}):"]
    for w in result.get("warnings", []):
        lines.append(f"    {w}")

    summary = result.get("summary", {})
    parts = []
    if summary.get("reductions"):
        parts.append(f"减持{summary['reductions']}笔")
    if summary.get("issuances"):
        parts.append(f"增发{summary['issuances']}笔")
    if summary.get("buybacks"):
        parts.append(f"回购{summary['buybacks']}笔")
    if parts:
        lines.append(f"    汇总: {', '.join(parts)}")

    return "\n".join(lines)
