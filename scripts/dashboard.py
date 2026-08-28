"""
意怠工程 — 持仓+信号 统一查询面板
"""
import sys, os, json, unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SIGNALS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "signals.duckdb")
KB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")


# ── 显示宽度工具 ──────────────────────────────────────────
def _dw(s):
    """计算字符串在终端中的显示宽度（CJK字符占2列）。"""
    w = 0
    for ch in str(s):
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def _pad(s, width, align="left"):
    """按显示宽度填充字符串到指定宽度。"""
    s = str(s)
    pad = width - _dw(s)
    if pad <= 0:
        return s
    if align == "right":
        return " " * pad + s
    return s + " " * pad


# ── 列定义 (显示宽度) ────────────────────────────────────
COLS = [
    ("代码", 10, "left"),
    ("名称", 14, "left"),
    ("持仓", 9, "right"),
    ("价格", 12, "right"),
    ("盈亏", 11, "right"),
    ("", 2, "center"),      # 箭头+间距
    ("评分", 6, "right"),
    (" ", 1, "center"),     # 分隔符
    ("评级", 3, "center"),
    (" ", 1, "center"),     # 分隔符
    ("信号", 8, "left"),
]


def _build_row(values):
    """根据列定义构建一行，精确对齐。"""
    parts = []
    for (label, width, align), val in zip(COLS, values):
        parts.append(_pad(val, width, align))
    return "  " + "".join(parts)


def _build_header():
    """构建表头，与数据行对齐。"""
    labels = ["代码", "名称", "持仓", "价格", "盈亏", "", "评分", "", "评级", "", "信号"]
    parts = []
    for (name, width, align), label in zip(COLS, labels):
        parts.append(_pad(label, width, align))
    return "  " + "".join(parts)


def _build_separator():
    return "  " + "─" * sum(w for _, w, _ in COLS)


# ── 数据加载 ──────────────────────────────────────────────
def load_portfolio():
    path = os.path.expanduser("~/.hermes/portfolio_data.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f).get("holdings", [])


def load_exchange_rates():
    path = os.path.expanduser("~/.hermes/portfolio_data.json")
    if not os.path.exists(path):
        return {"CNY_PER_HKD": 0.87, "USD_PER_HKD": 0.128}
    with open(path) as f:
        return json.load(f).get("exchange_rates", {"CNY_PER_HKD": 0.87, "USD_PER_HKD": 0.128})


def _normalize_ticker(t):
    return t.strip().upper().lstrip("0") or "0"


def get_latest_score(ticker):
    # Priority 1: Read from knowledge base (updated by `manage.py analyze`)
    try:
        from src.knowledge.base import KnowledgeBase
        kb = KnowledgeBase(KB_DIR)
        profile = kb.get_company_profile(ticker)
        if profile and profile.get("total"):
            # Get price from signal tracker (KB doesn't store prices)
            price = 0
            try:
                import duckdb
                conn = duckdb.connect(SIGNALS_DB, read_only=True)
                all_rows = conn.execute("SELECT * FROM signal_records ORDER BY signal_date DESC").fetchdf()
                conn.close()
                target = _normalize_ticker(ticker)
                for _, row in all_rows.iterrows():
                    if _normalize_ticker(row["ticker"]) == target:
                        state = json.loads(row["company_state"]) if row["company_state"] else {}
                        price = state.get("price", 0)
                        break
            except Exception:
                pass
            return {
                "signal": profile.get("signal", ""),
                "total_score": profile.get("total", 0),
                "grade": profile.get("grade", ""),
                "price": price,
                "scores": profile.get("scores", {}),
            }
    except Exception:
        pass

    # Priority 2: Fall back to signal tracker
    try:
        import duckdb
        conn = duckdb.connect(SIGNALS_DB, read_only=True)
        all_rows = conn.execute("SELECT * FROM signal_records ORDER BY signal_date DESC").fetchdf()
        conn.close()
        target = _normalize_ticker(ticker)
        for _, row in all_rows.iterrows():
            if _normalize_ticker(row["ticker"]) == target:
                scores = json.loads(row["dimension_scores"]) if row["dimension_scores"] else {}
                state = json.loads(row["company_state"]) if row["company_state"] else {}
                return {
                    "signal": row["signal_type"],
                    "total_score": row["total_score"],
                    "grade": row["grade"],
                    "price": state.get("price", 0),
                    "scores": scores,
                }
        return None
    except Exception:
        return None


# ── 主函数 ────────────────────────────────────────────────
def main():
    from src.knowledge.base import KnowledgeBase

    holdings = load_portfolio()
    if not holdings:
        print("  ❌ 未找到持仓数据 (~/.hermes/portfolio_data.json)")
        return

    kb = KnowledgeBase(KB_DIR)
    companies = kb.list_companies()
    company_map = {c["ticker"]: c for c in companies}
    rates = load_exchange_rates()
    cny_per_hkd = rates.get("CNY_PER_HKD", 0.87)

    # ── 收集数据 ──────────────────────────────────────────
    total_value = 0
    total_cost = 0
    rows_by_signal = {"BUY": [], "HOLD": [], "REDUCE": [], None: []}

    for h in holdings:
        ticker = h.get("ticker", "")
        name = h.get("name", ticker)
        shares = h.get("shares", 0)
        cost = h.get("avg_cost", 0)
        ccy = h.get("price_ccy", "HKD")

        score = get_latest_score(ticker)

        price = 0
        if score and score.get("price"):
            price = score["price"]

        if ccy == "USD":
            value_hkd = shares * price / rates.get("USD_PER_HKD", 0.128)
            cost_hkd = shares * cost / rates.get("USD_PER_HKD", 0.128)
        elif ccy == "CNY":
            value_hkd = shares * price / cny_per_hkd
            cost_hkd = shares * cost / cny_per_hkd
        else:
            value_hkd = shares * price
            cost_hkd = shares * cost

        total_value += value_hkd
        total_cost += cost_hkd
        pnl = value_hkd - cost_hkd
        pnl_pct = (pnl / cost_hkd * 100) if cost_hkd > 0 else 0

        signal = score.get("signal", None) if score else None
        total_score = score.get("total_score", None) if score else None
        grade = score.get("grade", "") if score else ""

        rows_by_signal.setdefault(signal, []).append({
            "ticker": ticker, "name": name, "shares": shares,
            "price": price, "pnl_pct": pnl_pct,
            "score": total_score, "grade": grade,
            "ccy": ccy,
        })

    # ── 格式化一行 ────────────────────────────────────────
    def fmt_price(p, ccy=""):
        if p > 1000:
            s = f"{p:,.0f}"
        elif p > 10:
            s = f"{p:.2f}"
        else:
            s = f"{p:.2f}"
        return f"{s} {ccy}" if ccy else s

    def fmt_row(r, sig_type):
        pnl = r["pnl_pct"]
        arrow = "↑" if pnl > 0 else "↓" if pnl < 0 else "→"
        score_str = f"{r['score']}/35" if r["score"] is not None else "N/A"
        return _build_row([
            r["ticker"],
            r["name"],
            f"{r['shares']:,}",
            fmt_price(r["price"], r.get("ccy", "")),
            f"{pnl:+.1f}%",
            arrow,
            score_str,
            " │ ",
            r["grade"],
            " │ ",
            sig_type or "",
        ])

    # ── 输出 ──────────────────────────────────────────────
    # ── 带框线的输出（按显示宽度对齐）──────────────────────
    BOX_W = 72  # 框内宽度（显示列）

    def box_line(content=""):
        """生成一行框线：║ content ║"""
        pad = BOX_W - _dw(content)
        if pad < 0:
            pad = 0
        return f"  ║{content}{' ' * pad}║"

    def box_top():
        return "  ╔" + "═" * BOX_W + "╗"

    def box_bot():
        return "  ╚" + "═" * BOX_W + "╝"

    def box_sep():
        return "  ├" + "─" * BOX_W + "┤"

    print()
    print(box_top())
    print(box_line("意怠工程 — 持仓 + 信号 统一面板"))
    print(box_bot())

    signal_order = ["BUY", "HOLD", "REDUCE", None]
    signal_labels = {
        "BUY":    "🟢 买入信号",
        "HOLD":   "🟡 持有信号",
        "REDUCE": "🔴 减仓信号",
        None:     "⚪ 无信号",
    }

    for sig in signal_order:
        rows = rows_by_signal.get(sig, [])
        if not rows:
            continue
        label = signal_labels.get(sig, "")
        print(f"\n  {label} ({len(rows)}家)")
        print(_build_header())
        print(_build_separator())
        for r in rows:
            print(fmt_row(r, sig))

    # ── 总览 ──────────────────────────────────────────────
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    pnl_icon = "📈" if total_pnl > 0 else "📉" if total_pnl < 0 else "➡️"

    print()
    print(box_top())
    print(box_line("组合总览"))
    print(box_sep())
    print(box_line(f"  总市值: {total_value:>12,.2f} HKD   成本: {total_cost:>12,.2f} HKD"))
    print(box_line(f"  盈亏:   {pnl_icon} {total_pnl:>11,.2f} HKD   ({total_pnl_pct:>+.1f}%)"))
    print(box_bot())

    BOX_W2 = 72

    def tip_line(content=""):
        pad = BOX_W2 - _dw(content)
        if pad < 0:
            pad = 0
        return f"  │{content}{' ' * pad}│"

    print()
    print("  ┌" + "─" * BOX_W2 + "┐")
    print(tip_line("💡 操作提示"))
    print(tip_line("  · 查看面板:  python manage.py dashboard"))
    print(tip_line("  · 更新信号:  python manage.py signals"))
    print(tip_line("  · 生成周报:  python manage.py report"))
    print(tip_line("  · 分析公司:  python manage.py analyze <ticker>"))
    print(tip_line("  · 知识库:    python manage.py kb"))
    print("  └" + "─" * BOX_W2 + "┘")
    print()


def main_enhanced():
    """Enhanced dashboard using the visualization module."""
    import json as _json

    holdings = load_portfolio()
    if not holdings:
        print("  ❌ 未找到持仓数据 (~/.hermes/portfolio_data.json)")
        return

    path = os.path.expanduser("~/.hermes/portfolio_data.json")
    with open(path) as f:
        raw = _json.load(f)

    # Build scores dict from knowledge base
    from src.knowledge.base import KnowledgeBase
    kb = KnowledgeBase(KB_DIR)
    scores = {}
    for h in holdings:
        ticker = h.get("ticker", "")
        score = get_latest_score(ticker)
        if score:
            scores[ticker] = score

    # Render portfolio dashboard
    try:
        from src.viz.dashboard import render_portfolio_dashboard, render_score_radar
        print(render_portfolio_dashboard(raw, scores))

        # Show radar for the first scored company
        if scores:
            first_ticker = list(scores.keys())[0]
            first_score = scores[first_ticker]
            dim_scores = first_score.get("scores", {})
            # Map Chinese dimension names to English
            cn_to_en = {
                "盈利": "profitability", "健康": "health", "现金流": "cashflow",
                "估值": "valuation", "成长": "growth", "股东": "ownership", "战略": "strategy",
            }
            eng_scores = {}
            for k, v in dim_scores.items():
                if isinstance(v, dict):
                    v = v.get("score", 0)
                eng_key = cn_to_en.get(k, k)
                eng_scores[eng_key] = int(v) if v is not None else 0

            print(f"  ── {first_ticker} 七维评分 ──")
            print(render_score_radar(eng_scores))
    except ImportError as e:
        print(f"  ⚠️ 可视化模块加载失败: {e}")
        print("  回退到经典面板...")
        main()


if __name__ == "__main__":
    main()
