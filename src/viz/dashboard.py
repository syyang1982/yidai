"""
意怠工程 — 终端数据可视化仪表盘

Terminal-based portfolio dashboard with:
- Portfolio summary (total value, total P&L, position count)
- Position table with grades and signals
- Signal distribution ASCII pie chart
- Top 3 risks from anomaly alerts
- 7-dimension radar chart using box-drawing characters

All output handles CJK double-width characters correctly.
"""

import unicodedata
from typing import Dict, List, Optional, Tuple


# ── CJK Double-Width Helpers ──────────────────────────────────────────────

def _display_width(s: str) -> int:
    """Calculate terminal display width (CJK chars count as 2)."""
    w = 0
    for ch in str(s):
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def _pad(s: str, width: int, align: str = "left") -> str:
    """Pad string to target display width, respecting CJK double-width."""
    s = str(s)
    pad = width - _display_width(s)
    if pad <= 0:
        return s
    if align == "right":
        return " " * pad + s
    elif align == "center":
        left = pad // 2
        right = pad - left
        return " " * left + s + " " * right
    return s + " " * pad


# ── Box Drawing Helpers ───────────────────────────────────────────────────

def _box_line(content: str, width: int, left: str = "║", right: str = "║") -> str:
    """Generate a single box line with proper padding."""
    pad = width - _display_width(content)
    if pad < 0:
        pad = 0
    return f"  {left}{content}{' ' * pad}{right}"


def _box_top(width: int) -> str:
    return "  ╔" + "═" * width + "╗"


def _box_bot(width: int) -> str:
    return "  ╚" + "═" * width + "╝"


def _box_sep(width: int) -> str:
    return "  ├" + "─" * width + "┤"


def _box_double_sep(width: int) -> str:
    return "  ╠" + "═" * width + "╣"


# ── Column Definitions ────────────────────────────────────────────────────

POSITION_COLS = [
    ("ticker", "代码", 12, "left"),
    ("name",   "名称", 14, "left"),
    ("shares", "持仓", 8,  "right"),
    ("cost",   "成本", 9,  "right"),
    ("price",  "现价", 9,  "right"),
    ("pnl",    "盈亏%", 8, "right"),
    ("weight", "权重%", 7, "right"),
    ("grade",  "评级", 5,  "center"),
]


# ── Portfolio Dashboard ───────────────────────────────────────────────────

def render_portfolio_dashboard(portfolio_data: dict, scores: dict) -> str:
    """
    Generate a rich terminal portfolio dashboard.

    Args:
        portfolio_data: dict with keys:
            - "holdings": list of dicts with ticker, name, shares, avg_cost, price_ccy
            - "prices": dict mapping ticker -> {price, currency}
            - "exchange_rates": dict with CNY_PER_HKD, USD_PER_HKD
            Optional:
            - "anomaly_alerts": list of risk/alert strings
        scores: dict mapping ticker -> score dict with keys:
            - "total_score", "grade", "signal", "price", "scores" (dim dict)

    Returns:
        str: Formatted terminal dashboard string.
    """
    lines: List[str] = []
    box_w = 78

    holdings = portfolio_data.get("holdings", [])
    prices = portfolio_data.get("prices", {})
    rates = portfolio_data.get("exchange_rates", {})
    cny_per_hkd = rates.get("CNY_PER_HKD", 0.87)
    usd_per_hkd = rates.get("USD_PER_HKD", 0.128)
    anomaly_alerts = portfolio_data.get("anomaly_alerts", [])

    # ── Header ────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(_box_top(box_w))
    lines.append(_box_line("  📊 意怠工程 — 投资组合仪表盘", box_w))
    lines.append(_box_bot(box_w))

    if not holdings:
        lines.append("")
        lines.append(_box_line("  ❌ 暂无持仓数据", box_w))
        lines.append("")
        return "\n".join(lines)

    # ── Compute position data ─────────────────────────────────────────────
    positions = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        ticker = h.get("ticker", "")
        name = h.get("name", ticker)
        shares = h.get("shares", 0)
        cost = h.get("avg_cost", 0)
        ccy = h.get("price_ccy", "HKD")

        # Get current price from prices dict or scores
        price_info = prices.get(ticker, {})
        price = price_info.get("price", 0)
        if not price and scores:
            s = scores.get(ticker, {})
            price = s.get("price", 0)

        # Convert to HKD for value calculation
        if ccy == "USD":
            value_hkd = shares * price / usd_per_hkd if usd_per_hkd else 0
            cost_hkd = shares * cost / usd_per_hkd if usd_per_hkd else 0
        elif ccy == "CNY":
            value_hkd = shares * price / cny_per_hkd if cny_per_hkd else 0
            cost_hkd = shares * cost / cny_per_hkd if cny_per_hkd else 0
        else:
            value_hkd = shares * price
            cost_hkd = shares * cost

        total_value += value_hkd
        total_cost += cost_hkd

        pnl_pct = ((value_hkd - cost_hkd) / cost_hkd * 100) if cost_hkd > 0 else 0

        # Score info
        score_info = scores.get(ticker, {}) if scores else {}
        grade = score_info.get("grade", "-")
        signal = score_info.get("signal", "")

        positions.append({
            "ticker": ticker,
            "name": name,
            "shares": shares,
            "cost": cost,
            "price": price,
            "ccy": ccy,
            "pnl_pct": pnl_pct,
            "value_hkd": value_hkd,
            "grade": grade,
            "signal": signal,
        })

    # Compute weights
    for p in positions:
        p["weight"] = (p["value_hkd"] / total_value * 100) if total_value > 0 else 0

    # Sort by value descending
    positions.sort(key=lambda p: p["value_hkd"], reverse=True)

    # ── Summary Section ───────────────────────────────────────────────────
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    pnl_icon = "📈" if total_pnl > 0 else "📉" if total_pnl < 0 else "➡️"

    lines.append("")
    lines.append(_box_top(box_w))
    lines.append(_box_line("  💰 组合总览", box_w))
    lines.append(_box_double_sep(box_w))
    lines.append(_box_line(
        f"  总市值: {total_value:>14,.2f} HKD    "
        f"持仓数: {len(positions)}", box_w
    ))
    lines.append(_box_line(
        f"  总成本: {total_cost:>14,.2f} HKD    "
        f"盈亏: {pnl_icon} {total_pnl:>+12,.2f} HKD ({total_pnl_pct:>+.1f}%)",
        box_w
    ))
    lines.append(_box_bot(box_w))

    # ── Position Table ────────────────────────────────────────────────────
    lines.append("")
    lines.append(_box_top(box_w))
    lines.append(_box_line("  📋 持仓明细", box_w))
    lines.append(_box_double_sep(box_w))

    # Header
    header_parts = []
    for _, label, width, align in POSITION_COLS:
        header_parts.append(_pad(label, width, align))
    lines.append(_box_line("  " + "  ".join(header_parts), box_w))
    lines.append(_box_sep(box_w))

    # Data rows
    for p in positions:
        pnl_str = f"{p['pnl_pct']:+.1f}%"
        arrow = "↑" if p["pnl_pct"] > 0 else "↓" if p["pnl_pct"] < 0 else "→"
        price_str = f"{p['price']:.2f} {p['ccy']}" if p["price"] else "N/A"

        row_vals = [
            p["ticker"],
            p["name"],
            f"{p['shares']:,}",
            f"{p['cost']:.2f}",
            price_str,
            f"{pnl_str} {arrow}",
            f"{p['weight']:.1f}%",
            p["grade"],
        ]
        row_parts = []
        for (_, _, width, align), val in zip(POSITION_COLS, row_vals):
            row_parts.append(_pad(val, width, align))
        lines.append(_box_line("  " + "  ".join(row_parts), box_w))

    lines.append(_box_bot(box_w))

    # ── Signal Distribution ───────────────────────────────────────────────
    signal_counts = {"BUY": 0, "HOLD": 0, "WATCH": 0, "REDUCE": 0}
    for p in positions:
        sig = p.get("signal", "")
        if sig in signal_counts:
            signal_counts[sig] += 1

    lines.append("")
    lines.append(_box_top(box_w))
    lines.append(_box_line("  🎯 信号分布", box_w))
    lines.append(_box_double_sep(box_w))

    total_signals = sum(signal_counts.values())
    signal_icons = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}
    signal_labels = {"BUY": "买入", "HOLD": "持有", "WATCH": "观望", "REDUCE": "减仓"}

    if total_signals > 0:
        # ASCII pie chart
        bar_width = 40
        for sig in ["BUY", "HOLD", "WATCH", "REDUCE"]:
            count = signal_counts[sig]
            pct = count / total_signals * 100
            bar_len = int(count / total_signals * bar_width)
            bar = "█" * bar_len + "░" * (bar_width - bar_len)
            icon = signal_icons[sig]
            label = signal_labels[sig]
            lines.append(_box_line(
                f"  {icon} {label}  [{bar}] {count}家 ({pct:.0f}%)",
                box_w
            ))
    else:
        lines.append(_box_line("  暂无信号数据", box_w))

    lines.append(_box_bot(box_w))

    # ── Top 3 Risks ───────────────────────────────────────────────────────
    lines.append("")
    lines.append(_box_top(box_w))
    lines.append(_box_line("  ⚠️  Top 3 风险提示", box_w))
    lines.append(_box_double_sep(box_w))

    risks = _extract_risks(positions, anomaly_alerts)
    for i, risk in enumerate(risks[:3], 1):
        lines.append(_box_line(f"  {i}. {risk}", box_w))

    # Pad if fewer than 3 risks
    for i in range(len(risks), 3):
        lines.append(_box_line(f"  {i+1}. —", box_w))

    lines.append(_box_bot(box_w))
    lines.append("")

    return "\n".join(lines)


def _extract_risks(positions: List[dict], anomaly_alerts: List[str]) -> List[str]:
    """Extract top risks from positions and anomaly alerts."""
    risks = []

    # From anomaly alerts (highest priority)
    if anomaly_alerts:
        risks.extend(anomaly_alerts[:3])

    # From positions: losing positions with significant loss
    losers = sorted(
        [p for p in positions if p.get("pnl_pct", 0) < -10],
        key=lambda p: p["pnl_pct"]
    )
    for p in losers:
        if len(risks) >= 3:
            break
        risk = f"{p['name']}({p['ticker']}) 亏损 {p['pnl_pct']:.1f}%，需关注"
        if risk not in risks:
            risks.append(risk)

    # From positions: concentrated positions
    concentrated = sorted(positions, key=lambda p: p.get("weight", 0), reverse=True)
    for p in concentrated:
        if len(risks) >= 3:
            break
        if p.get("weight", 0) > 25:
            risk = f"{p['name']}({p['ticker']}) 权重 {p['weight']:.1f}%，集中度偏高"
            if risk not in risks:
                risks.append(risk)

    # Default risk if none found
    if not risks:
        risks.append("暂无显著风险提示")

    return risks[:3]


# ── Radar Chart ───────────────────────────────────────────────────────────

# The 7 dimensions in display order
RADAR_DIMENSIONS = [
    ("profitability", "盈利"),
    ("health",        "健康"),
    ("cashflow",      "现金流"),
    ("valuation",     "估值"),
    ("growth",        "成长"),
    ("ownership",     "股东"),
    ("strategy",      "战略"),
]


def render_score_radar(scores: dict) -> str:
    """
    Render a 7-dimension radar chart in the terminal using box-drawing characters.

    Args:
        scores: dict mapping dimension names (English) to integer scores (0-5).
                Keys should be: profitability, health, cashflow, valuation,
                growth, ownership, strategy.

    Returns:
        str: Formatted terminal radar chart.
    """
    lines: List[str] = []
    box_w = 52

    lines.append("")
    lines.append(_box_top(box_w))
    lines.append(_box_line("  🎯 七维评分雷达图", box_w))
    lines.append(_box_double_sep(box_w))

    # Bar chart representation
    max_score = 5
    bar_chars = "░▒▓█"

    for dim_key, dim_label in RADAR_DIMENSIONS:
        score = scores.get(dim_key, 0)
        # Clamp to 0-5
        score = max(0, min(5, int(score) if score is not None else 0))

        # Build bar: filled portion uses █, empty uses ░
        filled = "█" * score
        empty = "░" * (max_score - score)

        # Color indicator
        if score >= 4:
            indicator = "🟢"
        elif score >= 3:
            indicator = "🟡"
        elif score >= 2:
            indicator = "🔵"
        else:
            indicator = "🔴"

        # Pad the label to handle CJK
        label_padded = _pad(dim_label, 8, "left")
        bar = f"[{filled}{empty}]"
        score_str = f"{score}/{max_score}"

        line = f"  {indicator} {label_padded} {bar} {score_str}"
        lines.append(_box_line(line, box_w))

    # Total
    total = sum(max(0, min(5, int(scores.get(k, 0) or 0))) for k, _ in RADAR_DIMENSIONS)
    lines.append(_box_sep(box_w))

    # Grade
    if total >= 29:
        grade = "A"
    elif total >= 22:
        grade = "B"
    elif total >= 15:
        grade = "C"
    elif total >= 8:
        grade = "D"
    else:
        grade = "F"

    lines.append(_box_line(f"  📊 总分: {total}/35  等级: {grade}", box_w))

    # ASCII radar-like visualization
    lines.append(_box_sep(box_w))
    lines.append(_box_line("  雷达示意:", box_w))

    # Simple ASCII radar using relative positions
    # Scale each score to a position on a 10-char radius
    radius = 10
    center_x, center_y = radius, radius

    # 7 points evenly spaced at angles: 0, 51.4, 102.9, ..., 308.6 degrees
    import math
    points = []
    for i, (dim_key, _) in enumerate(RADAR_DIMENSIONS):
        angle = math.radians(270 + i * 360 / 7)  # Start from top
        score = max(0, min(5, int(scores.get(dim_key, 0) or 0)))
        r = score / max_score * radius
        x = center_x + r * math.cos(angle)
        y = center_y + r * math.sin(angle)
        points.append((int(round(x)), int(round(y)), score))

    # Draw a simple grid
    grid_size = 2 * radius + 1
    grid = [[" " for _ in range(grid_size)] for _ in range(grid_size)]

    # Draw reference circle (level 3)
    ref_r = 3 / max_score * radius
    for angle_deg in range(0, 360, 10):
        angle = math.radians(angle_deg)
        rx = int(round(center_x + ref_r * math.cos(angle)))
        ry = int(round(center_y + ref_r * math.sin(angle)))
        if 0 <= rx < grid_size and 0 <= ry < grid_size:
            if grid[ry][rx] == " ":
                grid[ry][rx] = "·"

    # Draw data polygon
    for i in range(len(points)):
        x1, y1, _ = points[i]
        x2, y2, _ = points[(i + 1) % len(points)]
        _draw_line(grid, x1, y1, x2, y2, grid_size)

    # Draw points
    for x, y, score in points:
        if 0 <= x < grid_size and 0 <= y < grid_size:
            grid[y][x] = str(score)

    # Center marker
    if 0 <= center_x < grid_size and 0 <= center_y < grid_size:
        grid[center_y][center_x] = "+"

    # Render grid with labels
    # Add dimension labels around the border
    label_positions = []
    for i, (dim_key, dim_label) in enumerate(RADAR_DIMENSIONS):
        angle = math.radians(270 + i * 360 / 7)
        lx = int(round(center_x + (radius + 2) * math.cos(angle)))
        ly = int(round(center_y + (radius + 2) * math.sin(angle)))
        label_positions.append((lx, ly, dim_label))

    for row_idx, row in enumerate(grid):
        row_str = "".join(row)
        lines.append(_box_line(f"  {row_str}", box_w))

    # Labels below
    lines.append(_box_sep(box_w))
    label_line = "  "
    for _, dim_label in RADAR_DIMENSIONS:
        score_val = scores.get(_, 0) or 0
        score_val = max(0, min(5, int(score_val)))
        label_line += f"{_pad(dim_label, 6, 'left')}{score_val} "
    # Truncate if too long
    lines.append(_box_line(label_line[:box_w - 4], box_w))

    lines.append(_box_bot(box_w))
    lines.append("")

    return "\n".join(lines)


def _draw_line(grid: list, x1: int, y1: int, x2: int, y2: int, size: int) -> None:
    """Draw a line between two points on the grid using Bresenham's algorithm."""
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy

    while True:
        if 0 <= x1 < size and 0 <= y1 < size:
            if grid[y1][x1] == " ":
                grid[y1][x1] = "·"
        if x1 == x2 and y1 == y2:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x1 += sx
        if e2 < dx:
            err += dx
            y1 += sy
