"""卖出提醒模块 — 自动检测持仓是否进入卖出区间。

7种卖出触发条件:
  1. 止盈目标达成 (take_profit_pct / target_price)
  2. 估值过热 (PE历史分位 > 80% 且 PE > 30)
  3. 基本面恶化 (信号从BUY/HOLD降为REDUCE)
  4. 止损触发 (当前价 <= 止损价 或 亏损 > 50%)
  5. 过度获利 (浮盈 > take_profit_pct 且无持仓保护标记)
  6. 同行估值溢价 (PE > 同行中位数 × 2)
  7. 股息率压缩 (高息股股息率 < 1.5%)

每个 alert 包含:
  - severity: CRITICAL(止损) / WARNING(止盈) / INFO(估值偏热)
  - ticker, name, current_price, trigger_condition
  - suggested_action: "trim X%" / "full_exit" / "tighten_stop"
"""

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

# ── 数据路径 ───────────────────────────────────────────────────
BASE_DIR = os.path.expanduser("~/.hermes/yidai")
PORTFOLIO_PATH = os.path.expanduser("~/.hermes/portfolio_data.json")
SIGNALS_DB_PATH = os.path.join(BASE_DIR, "db", "signals.duckdb")


@dataclass
class SellAlert:
    """一条卖出提醒。"""
    ticker: str
    name: str
    severity: str        # CRITICAL / WARNING / INFO
    trigger: str         # 触发条件类型 (英文key)
    trigger_cn: str      # 触发条件中文描述
    current_price: float
    cost_basis: float
    pnl_pct: float       # 浮盈/浮亏百分比
    suggested_action: str  # 建议操作
    details: str = ""    # 补充说明


# ── 触发条件定义 ───────────────────────────────────────────────

def _load_portfolio() -> dict:
    """读取 portfolio_data.json。"""
    with open(PORTFOLIO_PATH) as f:
        return json.load(f)


def _load_latest_signals() -> dict:
    """从 signals.duckdb 读取每只持仓股的最新信号。

    Returns:
        dict keyed by ticker, value = signal row dict.
    """
    try:
        import duckdb
        db = duckdb.connect(SIGNALS_DB_PATH, read_only=True)
        rows = db.execute("""
            SELECT ticker, company_name, signal_type, total_score, grade,
                   company_state, signal_date
            FROM signal_records
            WHERE status = 'active'
            ORDER BY signal_date DESC
        """).fetchall()
        db.close()

        latest = {}
        for row in rows:
            ticker = row[0]
            if ticker not in latest:
                latest[ticker] = {
                    "ticker": ticker,
                    "company_name": row[1],
                    "signal_type": row[2],
                    "total_score": row[3],
                    "grade": row[4],
                    "company_state": json.loads(row[5]) if row[5] else {},
                    "signal_date": str(row[6]),
                }
        return latest
    except Exception:
        return {}


def _load_strategy_targets(portfolio: dict) -> dict:
    """从 portfolio_data.json 的 strategy.sell_targets 提取每只股的卖出目标。

    Returns:
        dict keyed by ticker, value = target config dict.
    """
    strategy = portfolio.get("strategy", {})
    # 兼容两种 key: sell_targets (当前) 和 targets (旧)
    targets = strategy.get("sell_targets", strategy.get("targets", {}))

    # 也检查 xiaomi 等独立策略块中的 sell_targets
    for key, val in strategy.items():
        if isinstance(val, dict) and "sell_targets" in val:
            targets.update(val["sell_targets"])

    return targets


def check_take_profit(
    ticker: str, name: str, price: float, cost: float,
    targets: dict, pnl: float,
) -> Optional[SellAlert]:
    """检查1: 止盈目标达成。"""
    t = targets.get(ticker, {})

    # 方式A: 目标价
    target_price = t.get("target_price")
    if target_price and price >= target_price:
        return SellAlert(
            ticker=ticker, name=name, severity="WARNING",
            trigger="target_price_hit",
            trigger_cn=f"达到目标价 {target_price}",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="考虑部分获利了结",
            details=f"当前价{price} >= 目标价{target_price}",
        )

    # 方式B: 止盈百分比
    tp_pct = t.get("take_profit_pct") or t.get("take_profit")
    # take_profit 如果是价格(>cost), 转为百分比
    if tp_pct and isinstance(tp_pct, (int, float)):
        if tp_pct > cost and cost > 0:
            tp_pct = (tp_pct - cost) / cost * 100
        if pnl >= tp_pct / 100.0:
            return SellAlert(
                ticker=ticker, name=name, severity="WARNING",
                trigger="take_profit_pct_hit",
                trigger_cn=f"浮盈{pnl:.0%}达到止盈线{tp_pct:.0f}%",
                current_price=price, cost_basis=cost, pnl_pct=pnl,
                suggested_action="考虑减仓1/3~1/2锁定利润",
                details=t.get("notes", ""),
            )

    return None


def check_valuation_overheated(
    ticker: str, name: str, price: float, cost: float,
    signal_info: dict, pnl: float,
) -> Optional[SellAlert]:
    """检查2: 估值过热 — PE历史分位 > 80% 且 PE > 30。"""
    state = signal_info.get("company_state", {})
    pe = state.get("pe", state.get("pe_ratio", 0)) or 0
    pe_pct = state.get("pe_history_percentile", 0.5) or 0.5

    if pe > 30 and pe_pct > 0.80:
        return SellAlert(
            ticker=ticker, name=name, severity="WARNING",
            trigger="valuation_overheated",
            trigger_cn=f"PE={pe:.1f}x, 历史分位{pe_pct:.0%}",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="估值偏高, 考虑减仓或收紧止损",
            details=f"PE {pe:.1f}x处于历史{pe_pct:.0%}分位, 高于30x",
        )
    return None


def check_fundamental_deterioration(
    ticker: str, name: str, price: float, cost: float,
    signal_info: dict, pnl: float,
) -> Optional[SellAlert]:
    """检查3: 基本面恶化 — 当前信号为REDUCE。"""
    signal_type = signal_info.get("signal_type", "")
    score = signal_info.get("total_score", 0)

    if signal_type == "REDUCE":
        return SellAlert(
            ticker=ticker, name=name, severity="CRITICAL",
            trigger="fundamental_deterioration",
            trigger_cn=f"信号REDUCE, 评分{score}/40",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="基本面恶化, 建议减仓或清仓",
            details=f"意怠评分{score}/40触发REDUCE信号",
        )
    return None


def check_stop_loss(
    ticker: str, name: str, price: float, cost: float,
    targets: dict, pnl: float,
) -> Optional[SellAlert]:
    """检查4: 止损触发。"""
    t = targets.get(ticker, {})

    # 方式A: 硬止损 — 亏损 > 50%
    if pnl < -0.50:
        return SellAlert(
            ticker=ticker, name=name, severity="CRITICAL",
            trigger="hard_stop_loss",
            trigger_cn=f"亏损{pnl:.0%}, 超过50%硬止损线",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="立即止损清仓",
            details=f"浮亏{pnl:.0%}已超过50%硬止损线",
        )

    # 方式B: 止损价触发
    stop_price = t.get("stop_loss") or t.get("stop_loss_price") or t.get("stop_price")
    if stop_price and price <= stop_price:
        return SellAlert(
            ticker=ticker, name=name, severity="CRITICAL",
            trigger="stop_loss_price_hit",
            trigger_cn=f"当前价{price} <= 止损价{stop_price}",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="触发止损, 建议清仓",
            details=f"价格已跌破预设止损位{stop_price}",
        )

    # 方式C: 止损百分比
    sl_pct = t.get("stop_loss_pct")
    if sl_pct and pnl <= sl_pct / 100.0:
        return SellAlert(
            ticker=ticker, name=name, severity="CRITICAL",
            trigger="stop_loss_pct_hit",
            trigger_cn=f"浮亏{pnl:.0%}达到止损线{sl_pct}%",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="触发止损, 建议清仓",
            details=t.get("notes", ""),
        )

    return None


def check_excessive_gain(
    ticker: str, name: str, price: float, cost: float,
    targets: dict, pnl: float,
) -> Optional[SellAlert]:
    """检查5: 过度获利 — 浮盈超过阈值且无保护标记。

    对于没有设置 take_profit 的持仓, 如果浮盈 > 80% 也提醒。
    """
    t = targets.get(ticker, {})
    # 如果已经有止盈设置, 跳过(由 check_take_profit 处理)
    if t.get("take_profit_pct") or t.get("target_price"):
        return None

    # 无保护的高浮盈
    if pnl >= 0.80:
        return SellAlert(
            ticker=ticker, name=name, severity="INFO",
            trigger="excessive_unprotected_gain",
            trigger_cn=f"浮盈{pnl:.0%}, 未设止盈目标",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="建议设置止盈目标或移动止损",
            details="持仓浮盈显著但未设置止盈保护",
        )
    return None


def check_peer_premium(
    ticker: str, name: str, price: float, cost: float,
    signal_info: dict, pnl: float,
) -> Optional[SellAlert]:
    """检查6: 同行估值溢价 — PE > 同行中位数 × 2。"""
    state = signal_info.get("company_state", {})
    pe = state.get("pe", state.get("pe_ratio", 0)) or 0
    peer_pe = state.get("peer_median_pe", 0) or 0

    if pe > 0 and peer_pe > 0 and pe > peer_pe * 2:
        return SellAlert(
            ticker=ticker, name=name, severity="INFO",
            trigger="extreme_peer_premium",
            trigger_cn=f"PE {pe:.1f}x >> 同行中位 {peer_pe:.1f}x",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="估值显著高于同行, 注意回调风险",
            details=f"PE溢价{(pe/peer_pe - 1)*100:.0f}%",
        )
    return None


def check_dividend_yield_compression(
    ticker: str, name: str, price: float, cost: float,
    signal_info: dict, pnl: float,
) -> Optional[SellAlert]:
    """检查7: 高息股股息率压缩。"""
    state = signal_info.get("company_state", {})
    div_yield = state.get("dividend_yield", 0) or 0
    # 只对之前是高息股(>3%)且现在压缩到<1.5%的情况提醒
    prev_yield = state.get("prev_dividend_yield", 0) or 0

    if prev_yield > 0.03 and div_yield < 0.015:
        return SellAlert(
            ticker=ticker, name=name, severity="INFO",
            trigger="dividend_yield_compression",
            trigger_cn=f"股息率从{prev_yield:.1%}压缩至{div_yield:.1%}",
            current_price=price, cost_basis=cost, pnl_pct=pnl,
            suggested_action="股息率大幅下降, 考虑兑现",
            details="股价上涨导致股息率吸引力下降",
        )
    return None


# ── 主扫描函数 ─────────────────────────────────────────────────

def scan_sell_alerts(
    portfolio: Optional[dict] = None,
    signals: Optional[dict] = None,
    targets: Optional[dict] = None,
) -> List[SellAlert]:
    """扫描所有持仓, 返回触发的卖出提醒列表。

    按 severity 排序: CRITICAL > WARNING > INFO。
    """
    if portfolio is None:
        portfolio = _load_portfolio()
    if signals is None:
        signals = _load_latest_signals()
    if targets is None:
        targets = _load_strategy_targets(portfolio)

    # 构建价格映射
    prices = {}
    for p in portfolio.get("prices", []):
        # prices 是 list of dicts 或 dict
        pass
    # prices 可能是 dict keyed by ticker
    price_map = portfolio.get("prices", {})
    if isinstance(price_map, list):
        price_map = {p["ticker"]: p for p in price_map}

    alerts: List[SellAlert] = []
    seen_tickers = set()

    for holding in portfolio.get("holdings", []):
        ticker = holding["ticker"]
        name = holding.get("name", ticker)
        cost = holding.get("avg_cost", 0)
        shares = holding.get("shares", 0)

        if shares <= 0 or cost <= 0:
            continue

        # 获取当前价
        price_info = price_map.get(ticker, {})
        price = price_info.get("price", 0) if isinstance(price_info, dict) else 0
        if price <= 0:
            continue

        pnl = (price - cost) / cost

        # 获取信号信息
        sig = signals.get(ticker, {})

        # 运行7项检查
        checks = [
            check_stop_loss(ticker, name, price, cost, targets, pnl),
            check_fundamental_deterioration(ticker, name, price, cost, sig, pnl),
            check_take_profit(ticker, name, price, cost, targets, pnl),
            check_valuation_overheated(ticker, name, price, cost, sig, pnl),
            check_excessive_gain(ticker, name, price, cost, targets, pnl),
            check_peer_premium(ticker, name, price, cost, sig, pnl),
            check_dividend_yield_compression(ticker, name, price, cost, sig, pnl),
        ]

        for alert in checks:
            if alert is not None:
                alerts.append(alert)

    # 按 severity 排序
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.severity, 9), a.ticker))

    return alerts


# ── 格式化输出 ─────────────────────────────────────────────────

def _dw(s: str) -> int:
    """CJK-aware display width."""
    import unicodedata
    w = 0
    for ch in str(s):
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def _pad(s: str, width: int, align: str = "left") -> str:
    """Pad string to target display width."""
    s = str(s)
    pad = width - _dw(s)
    if pad <= 0:
        return s
    if align == "right":
        return " " * pad + s
    return s + " " * pad


def format_alerts_table(alerts: List[SellAlert]) -> str:
    """将卖出提醒列表格式化为框线表格。"""
    if not alerts:
        return "  ✅ 无卖出提醒 — 所有持仓均在安全区间"

    severity_icons = {
        "CRITICAL": "🔴",
        "WARNING": "🟡",
        "INFO": "🔵",
    }

    # 列宽: 公司12, 代码9, 严重度6, 触发条件22, 浮盈8, 建议22
    cw = [12, 9, 6, 22, 8, 22]
    headers = ["公司", "代码", "级别", "触发条件", "浮盈", "建议操作"]

    cell_ws = [w + 2 for w in cw]

    def hline(left, mid, right):
        return left + mid.join("─" * w for w in cell_ws) + right

    def fmt_row(cells):
        parts = []
        for cell, w in zip(cells, cw):
            parts.append(" " + _pad(str(cell), w) + " ")
        return "│" + "│".join(parts) + "│"

    lines = [
        "  " + hline("┌", "┬", "┐"),
        "  " + fmt_row(headers),
        "  " + hline("├", "┼", "┤"),
    ]

    for a in alerts:
        icon = severity_icons.get(a.severity, "⚪")
        pnl_str = f"{a.pnl_pct:+.0%}"
        row = [
            a.name,
            a.ticker,
            f"{icon} {a.severity[:3]}",
            a.trigger_cn[:22],
            pnl_str,
            a.suggested_action[:20],
        ]
        lines.append("  " + fmt_row(row))

    lines.append("  " + hline("└", "┴", "┘"))
    return "\n".join(lines)


def format_alerts_detail(alerts: List[SellAlert]) -> str:
    """详细格式 — 每条 alert 一个段落。"""
    if not alerts:
        return "  ✅ 无卖出提醒"

    severity_icons = {
        "CRITICAL": "🔴",
        "WARNING": "🟡",
        "INFO": "🔵",
    }

    sections = []
    for a in alerts:
        icon = severity_icons.get(a.severity, "⚪")
        lines = [
            f"  {icon} [{a.severity}] {a.name} ({a.ticker})",
            f"     触发: {a.trigger_cn}",
            f"     当前价: {a.current_price}  成本: {a.cost_basis}  浮盈: {a.pnl_pct:+.1%}",
            f"     建议: {a.suggested_action}",
        ]
        if a.details:
            lines.append(f"     备注: {a.details}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
