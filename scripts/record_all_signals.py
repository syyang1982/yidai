"""
意怠工程 — 全量信号记录
从知识库读取12家公司，拉取最新数据，七维评分，记录信号。
API失败时自动回退到DuckDB缓存数据。
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime
from src.data.fetcher import EastmoneyFetcher
from src.data.store import YidaiStore
from src.analysis.scorer import score_all
from src.knowledge.base import KnowledgeBase
from src.strategy.signal_tracker import SignalTracker
import unicodedata


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


def _render_table(headers, rows, col_widths, indent="  "):
    """渲染带框线的终端表格，正确处理CJK双宽字符。

    headers: 列名列表
    rows: 数据行列表 (每行是字符串列表)
    col_widths: 每列的内容区显示宽度
    """
    n = len(headers)
    cell_ws = [w + 2 for w in col_widths]  # +2 for 左右各1空格

    def horiz(left, mid, right):
        return left + mid.join("─" * cw for cw in cell_ws) + right

    def fmt_row(cells):
        parts = []
        for cell, w in zip(cells, col_widths):
            parts.append(" " + _pad(str(cell), w) + " ")
        return "│" + "│".join(parts) + "│"

    lines = [
        indent + horiz("┌", "┬", "┐"),
        indent + fmt_row(headers),
        indent + horiz("├", "┼", "┤"),
    ]
    for row in rows:
        lines.append(indent + fmt_row(row))
    lines.append(indent + horiz("└", "┴", "┘"))
    return "\n".join(lines)


DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
DB_PATH = os.path.join(DB_DIR, "yidai.duckdb")
SIGNALS_DB = os.path.join(DB_DIR, "signals.duckdb")

# LX hardcoded FY2025 values (USD)
LX_FINANCIAL = {
    "ticker": "LX",
    "period": "FY2025",
    "report_date": "2025-12-31",
    "revenue": 13_152_000_000,
    "net_income": 1_677_000_000,
    "gross_profit": 4_469_000_000,
    "total_assets": 23_163_000_000,
    "total_liabilities": 11_210_000_000,
    "total_equity": 11_953_000_000,
    "operating_cash_flow": 3_614_000_000,
    "free_cash_flow": 3_262_000_000,
}
LX_PRICE = {
    "ticker": "LX",
    "date": date.today().isoformat(),
    "close_price": 2.45,
    "market_cap": None,
    "pe_ratio": 2.04,
    "pb_ratio": None,
    "ps_ratio": None,
}
LX_PREV_FINANCIAL = {
    "revenue": 14_204_000_000,
}


def get_qualitative_scores(profile: dict) -> dict:
    """Extract ownership and strategy scores from KB profile."""
    scores = profile.get("scores", {})
    ownership = 3  # default (neutral, not assessed)
    strategy = 3   # default (neutral, not assessed)
    if "股东" in scores:
        val = scores["股东"]
        ownership = val.get("score", 3) if isinstance(val, dict) else int(val)
    if "战略" in scores:
        val = scores["战略"]
        strategy = val.get("score", 3) if isinstance(val, dict) else int(val)
    return {"ownership_score": ownership, "strategy_score": strategy}


def fetch_financials_with_fallback(fetcher, store, ticker):
    """Fetch financials from API, fall back to DuckDB cache if empty."""
    try:
        all_fin = fetcher.fetch_financials(ticker, periods=10)
        if all_fin:
            annual = sorted(
                [f for f in all_fin if isinstance(f, dict) and f.get("period", "").endswith("12-31")],
                key=lambda x: x.get("period", ""),
            )
            if annual:
                return annual
    except Exception:
        pass

    # Fallback: try DuckDB cache
    cached = store.get_financials(ticker)
    if cached:
        annual = [f for f in cached if f.get("period", "") and str(f.get("period", "")).endswith("12-31")]
        if annual:
            return sorted(annual, key=lambda x: str(x.get("period", "")))

    return []


def fetch_price_with_fallback(fetcher, store, ticker):
    """Fetch price from API, fall back to DuckDB cache if None."""
    price = None
    try:
        price = fetcher.fetch_price(ticker)
        if price is None or (price.get("close_price") is None and price.get("pe_ratio") is None):
            price = None
    except Exception:
        price = None

    if price is None:
        # Fallback: DuckDB cache
        cached = store.get_latest_price(ticker)
        if cached:
            return cached
        # Last resort: empty dict
        return {"ticker": ticker, "date": date.today().isoformat(),
                "close_price": None, "market_cap": None, "pe_ratio": None,
                "pb_ratio": None, "ps_ratio": None}

    return price


def process_company(fetcher, store, kb, ticker, signal_date, tracker):
    """Process one company: fetch data, score, record signal."""
    profile = kb.get_company_profile(ticker)
    name = profile.get("name", ticker)
    display_ticker = profile.get("ticker", ticker)

    # Skip LX for financial fetch (use hardcoded)
    if display_ticker == "LX" or ticker == "LX":
        fin = LX_FINANCIAL
        prev_fin = LX_PREV_FINANCIAL
        price = LX_PRICE
        annual = [LX_PREV_FINANCIAL, LX_FINANCIAL]  # for growth calc
    else:
        # Fetch financials with cache fallback
        annual = fetch_financials_with_fallback(fetcher, store, display_ticker)
        if len(annual) < 1:
            print(f"  ⚠️ {name} ({display_ticker}): 无财务数据（API+缓存均无），跳过")
            return None
        fin = annual[-1]
        prev_fin = annual[-2] if len(annual) >= 2 else None

        # Fetch price with cache fallback
        price = fetch_price_with_fallback(fetcher, store, display_ticker)

        # Special: 002352.SZ fallback PE from financial data
        if display_ticker == "002352.SZ" and price.get("pe_ratio") is None:
            pe_from_fin = fin.get("pe_ratio") or fin.get("PE")
            if pe_from_fin is not None:
                try:
                    price["pe_ratio"] = float(pe_from_fin)
                except (ValueError, TypeError):
                    pass

    # Get qualitative scores from existing KB profile
    qual = get_qualitative_scores(profile)

    # Run 7-dimension scoring
    result = score_all(fin, price, qual, prev_fin, all_annual_data=annual)

    # Build company_state for signal record
    revenue = fin.get("revenue", 0) or 0
    net_income = fin.get("net_income", 0) or 0
    company_state = {
        "price": price.get("close_price") or 0,
        "pe": price.get("pe_ratio"),
        "pb": price.get("pb_ratio"),
        "revenue": revenue,
        "net_income": net_income,
        "total_assets": fin.get("total_assets", 0) or 0,
        "total_liabilities": fin.get("total_liabilities", 0) or 0,
        "total_equity": fin.get("total_equity", 0) or 0,
        "operating_cash_flow": fin.get("operating_cash_flow", 0) or 0,
        "free_cash_flow": fin.get("free_cash_flow", 0) or 0,
        "gross_profit": fin.get("gross_profit", 0) or 0,
    }

    # Build dimension_scores dict
    dimension_scores = {
        "盈利": result["profitability_score"],
        "健康": result["health_score"],
        "现金流": result["cashflow_score"],
        "估值": result["valuation_score"],
        "成长": result["growth_score"],
        "股东": result["ownership_score"],
        "战略": result["strategy_score"],
    }

    # Build analysis_details
    details = result.get("details", [])
    analysis_details = {
        "profitability": details[:3] if len(details) >= 3 else details,
        "health": details[3:6] if len(details) >= 6 else [],
        "cashflow": details[6:9] if len(details) >= 9 else [],
        "valuation": details[9:12] if len(details) >= 12 else [],
        "growth": details[12:15] if len(details) >= 15 else [],
    }

    # Record signal
    signal_id = tracker.record_signal(
        ticker=display_ticker,
        company_name=name,
        signal_date=signal_date,
        signal_type=result["signal"],
        company_state=company_state,
        dimension_scores=dimension_scores,
        total_score=result["total_score"],
        grade=result["grade"],
        analysis_details=analysis_details,
        signal_source="七维评分",
    )

    # Auto-record action as system record
    tracker.record_action(
        signal_id=signal_id,
        user_action="系统记录",
        user_shares=0,
        user_price=0,
        user_date=signal_date,
        user_reason="系统自动记录，非用户操作",
    )

    return {
        "signal_id": signal_id,
        "ticker": display_ticker,
        "name": name,
        "signal": result["signal"],
        "total_score": result["total_score"],
        "grade": result["grade"],
        "scores": dimension_scores,
        "price": price.get("close_price"),
        "pe": price.get("pe_ratio"),
    }


def main():
    print("=" * 65)
    print("  意怠工程 — 全量信号记录")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 65)

    fetcher = EastmoneyFetcher()
    kb = KnowledgeBase()
    os.makedirs(DB_DIR, exist_ok=True)

    store = YidaiStore(DB_PATH)
    tracker = SignalTracker(SIGNALS_DB)

    signal_date = date.today().isoformat()

    # List all companies from KB
    companies = kb.list_companies()
    if not companies:
        print("❌ 知识库中没有公司档案")
        store.close()
        return

    print(f"\n找到 {len(companies)} 家公司，开始处理...\n")

    results = []
    errors = []

    for comp in companies:
        ticker = comp["ticker"]
        name = comp["name"]
        print(f"  处理: {name} ({ticker}) ...", end=" ", flush=True)
        try:
            result = process_company(fetcher, store, kb, ticker, signal_date, tracker)
            if result:
                results.append(result)
                emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(result["signal"], "❓")
                print(f"{emoji} {result['signal']} {result['total_score']}/35 {result['grade']}")
            else:
                errors.append((ticker, "数据不足"))
                print("⚠️ 数据不足")
        except Exception as e:
            errors.append((ticker, str(e)))
            print(f"❌ 错误: {e}")
            traceback.print_exc()

    store.close()

    # Summary table (box-drawing, CJK-aware)
    print(f"\n{'=' * 75}")
    print("  信号记录汇总")
    print(f"{'=' * 75}")

    if results:
        dim_keys = ["盈利", "健康", "现金流", "估值", "成长", "股东", "战略"]
        dim_hdrs = ["盈利", "健康", "现金流", "估值", "增长", "股东", "战略"]
        #   公司   代码    信号     总分 等级  盈利 健康 现金流 估值 增长 股东 战略 价格     PE
        cw = [10,    9,      9,      4,   4,   4,  4,   6,   4,  4,  4,  4,  7,      6]
        headers = ["公司", "代码", "信号", "总分", "等级"] + dim_hdrs + ["价格", "PE"]

        data_rows = []
        for r in sorted(results, key=lambda x: x["total_score"], reverse=True):
            emoji = {"BUY": "🟢", "HOLD": "🟡", "WATCH": "🔵", "REDUCE": "🔴"}.get(r["signal"], "❓")
            s = r["scores"]
            price_str = f"{r['price']:.2f}" if r["price"] else "N/A"
            pe_str = f"{r['pe']:.1f}" if r["pe"] else "N/A"
            signal_cell = f"{emoji} {r['signal']}"
            row = [r["name"], r["ticker"], signal_cell,
                   str(r["total_score"]), r["grade"]]
            for key in dim_keys:
                row.append(str(s[key]))
            row.extend([price_str, pe_str])
            data_rows.append(row)

        print()
        print(_render_table(headers, data_rows, cw))

    if errors:
        print(f"\n  ⚠️ 以下公司处理失败:")
        for ticker, reason in errors:
            print(f"    {ticker}: {reason}")

    # Stats
    print(f"\n  成功: {len(results)}/{len(companies)} 家公司")
    print(f"  信号数据库: {SIGNALS_DB}")
    print(f"  信号日期: {signal_date}")
    print(f"\n✅ 信号记录完成")


if __name__ == "__main__":
    main()
