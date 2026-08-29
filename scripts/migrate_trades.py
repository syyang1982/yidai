#!/usr/bin/env python3
"""
Migrate trade-log.md (40 trades) → decision_log table in signals.duckdb
"""

import re
import json
import hashlib
import os
from datetime import datetime

import duckdb

# Paths
TRADE_LOG = os.path.expanduser("~/.hermes/trading/trade-log.md")
DB_PATH = os.path.expanduser("~/.hermes/yidai/db/signals.duckdb")
KNOWLEDGE_DIR = os.path.expanduser("~/.hermes/yidai/knowledge/companies")

# Ticker mapping: trade-log name → (ticker, market, company_name, currency)
TICKER_MAP = {
    "LX": ("LX", "US", "LexinFintech", "USD"),
    "Xiaomi": ("01810.HK", "HK", "小米集团", "HKD"),
    "Xiaomi Add": ("01810.HK", "HK", "小米集团", "HKD"),
    "ANTA": ("02020.HK", "HK", "安踏体育", "HKD"),
    "ANTA Sports": ("02020.HK", "HK", "安踏体育", "HKD"),
    "Weimob": ("02252.HK", "HK", "微创机器人", "HKD"),
    "Weimob Swing": ("02252.HK", "HK", "微创机器人", "HKD"),
    "Medbot": ("02252.HK", "HK", "微创机器人", "HKD"),
    "Medbot/Weimob": ("02252.HK", "HK", "微创机器人", "HKD"),
    "RoboSense": ("02498.HK", "HK", "速腾聚创", "HKD"),
    "Kingsoft SW": ("03888.HK", "HK", "金山软件", "HKD"),
    "Kingsoft Cloud": ("03896.HK", "HK", "金山云", "HKD"),
    "Bilibili": ("09626.HK", "HK", "哔哩哔哩", "HKD"),
    "MINISO": ("09896.HK", "HK", "名创优品", "HKD"),
    "NetEase": ("09999.HK", "HK", "网易", "HKD"),
    "Alibaba": ("09988.HK", "HK", "阿里巴巴", "HKD"),
    "CMB": ("600036.SH", "SH", "招商银行", "CNY"),
    "China Merchants Bank": ("600036.SH", "SH", "招商银行", "CNY"),
    "361 Degrees": ("1361.HK", "HK", "361度国际有限公司", "HKD"),
    "Stockland": ("SGP.AX", "AX", "Stockland Group", "AUD"),
}

# Known dimension scores from knowledge/companies files
# Format: ticker → {dimension: score}
COMPANY_SCORES = {}


def load_company_scores():
    """Load dimension scores from knowledge/companies/*.md files."""
    scores = {}
    if not os.path.isdir(KNOWLEDGE_DIR):
        return scores
    for fname in os.listdir(KNOWLEDGE_DIR):
        if not fname.endswith(".md"):
            continue
        ticker = fname.replace(".md", "")
        # Normalize: 01810.HK → 01810.HK (keep as-is)
        filepath = os.path.join(KNOWLEDGE_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        dim_scores = {}
        # Parse markdown table rows like: | 盈利 | 5/5 | ↑ |
        for m in re.finditer(r"\|\s*(盈利|健康|现金流|估值|成长|股东|战略)\s*\|\s*(\d+)/(\d+)\s*\|", content):
            dim_name = m.group(1)
            score = int(m.group(2))
            dim_scores[dim_name] = {"score": score, "details": []}

        if dim_scores:
            scores[ticker] = dim_scores
    return scores


def resolve_ticker(name):
    """Resolve trade-log ticker name to (ticker, market, company_name, currency)."""
    # Try exact match first
    if name in TICKER_MAP:
        return TICKER_MAP[name]
    # Try case-insensitive
    for key, val in TICKER_MAP.items():
        if key.lower() == name.lower():
            return val
    # Try substring match (e.g. "ANTA Sports PARTIAL SELL" contains "ANTA Sports")
    for key, val in TICKER_MAP.items():
        if key.lower() in name.lower() or name.lower() in key.lower():
            return val
    return (name, "UNKNOWN", name, "UNKNOWN")


def parse_trade_log(path):
    """Parse trade-log.md and extract all trades."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    trades = []

    # Pattern: ### Trade #NNN — Name (optional details)
    # Followed by structured fields
    trade_pattern = re.compile(
        r"###\s*Trade\s*#(\d+)\s*[—–-]\s*(.+?)(?:\n|$)", re.MULTILINE
    )

    for match in trade_pattern.finditer(content):
        trade_num = int(match.group(1))
        trade_title = match.group(2).strip()

        # Extract the trade block (until next ### or --- or end)
        start = match.end()
        next_section = re.search(r"\n(?:###|---|\*\*)", content[start:])
        end = start + next_section.start() if next_section else len(content)
        block = content[start:end]

        # Parse fields
        trade = {
            "trade_num": trade_num,
            "title": trade_title,
            "action": None,
            "shares": None,
            "price": None,
            "currency": "HKD",
            "date": None,
            "status": None,
            "notes": "",
            "p_l": None,
            "realized_gain": None,
        }

        # Extract action line
        action_match = re.search(
            r"- Action:\s*(BUY|SELL)\s*([\d,]+)\s*shares?\s*@\s*(?:USD|US|HK|CNY|A\$)?\$?([\d.,]+)",
            block,
        )
        if action_match:
            trade["action"] = action_match.group(1)
            trade["shares"] = int(action_match.group(2).replace(",", ""))
            trade["price"] = float(action_match.group(3).replace(",", ""))

        # Extract date
        date_match = re.search(r"- Date:\s*(\d{4}-\d{2}-\d{2})", block)
        if date_match:
            trade["date"] = date_match.group(1)

        # Extract status
        status_match = re.search(r"- Status:\s*(OPEN|CLOSED)", block)
        if status_match:
            trade["status"] = status_match.group(1)

        # Extract P/L
        pl_match = re.search(r"- P/L:\s*([+-][\d.]+)%", block)
        if pl_match:
            trade["p_l"] = float(pl_match.group(1))

        # Extract realized gain
        gain_match = re.search(r"- Realized gain:\s*(?:HK\$|CNY)?([+-][\d,]+(?:\.\d+)?)", block)
        if not gain_match:
            gain_match = re.search(r"Realized gain:\s*(?:HK\$|CNY)?([+-][\d,]+(?:\.\d+)?)", block)
        if gain_match:
            trade["realized_gain"] = float(gain_match.group(1).replace(",", ""))

        # Extract realized loss
        loss_match = re.search(r"- Realized loss:\s*(?:HK\$|CNY)?([+-][\d,]+(?:\.\d+)?)", block)
        if not loss_match:
            loss_match = re.search(r"Realized loss:\s*(?:HK\$|CNY)?([+-][\d,]+(?:\.\d+)?)", block)
        if loss_match:
            trade["realized_gain"] = float(loss_match.group(1).replace(",", ""))

        # Extract notes
        notes_match = re.search(r"- Notes:\s*(.+?)(?:\n|$)", block)
        if notes_match:
            trade["notes"] = notes_match.group(1).strip()

        # Extract closed via
        closed_match = re.search(r"- Closed via:\s*(.+?)(?:\n|$)", block)
        if closed_match:
            trade["closed_via"] = closed_match.group(1).strip()

        # Determine currency from action line
        if "USD" in block or "US$" in block:
            trade["currency"] = "USD"
        elif "CNY" in block:
            trade["currency"] = "CNY"
        elif "A$" in block:
            trade["currency"] = "AUD"

        # Parse ticker name from title
        # Title format: "Name (TICKER) optional" or just "Name"
        ticker_match = re.match(r"(.+?)\s*\(([^)]+)\)", trade_title)
        if ticker_match:
            trade["name"] = ticker_match.group(1).strip()
            trade["ticker_hint"] = ticker_match.group(2).strip()
        else:
            trade["name"] = trade_title
            trade["ticker_hint"] = None

        trades.append(trade)

    return trades


def make_decision_id(trade_num):
    """Generate a deterministic decision_id from trade number."""
    return hashlib.md5(f"trade-log-{trade_num:03d}".encode()).hexdigest()[:8]


def build_decision_record(trade, company_scores):
    """Convert a parsed trade dict into a decision_log row dict."""
    name = trade["name"]

    # Resolve ticker
    ticker, market, company_name, default_currency = resolve_ticker(name)
    currency = trade["currency"] if trade["currency"] != "UNKNOWN" else default_currency

    # Calculate amount
    amount = 0.0
    if trade["shares"] and trade["price"]:
        amount = trade["shares"] * trade["price"]

    # Determine action
    action = trade.get("action", "BUY")
    if action is None:
        action = "BUY"  # default

    # Status mapping
    status = "open"
    if trade.get("status") == "CLOSED":
        status = "closed"

    # actual_return_pct for closed trades
    actual_return_pct = None
    if status == "closed" and trade.get("p_l") is not None:
        actual_return_pct = trade["p_l"]

    # Look up dimension scores from company knowledge files
    dim_scores = None
    total_score = 0

    # Try multiple ticker variants for lookup
    lookup_keys = [ticker]
    if trade.get("ticker_hint"):
        lookup_keys.append(trade["ticker_hint"])

    for key in lookup_keys:
        if key in company_scores:
            dim_scores = company_scores[key]
            # Calculate total score
            total_score = sum(
                v["score"] for v in dim_scores.values() if isinstance(v, dict) and "score" in v
            )
            break

    # Grade based on total score (if we have 7 dimensions max 35)
    grade = ""
    if total_score > 0:
        if total_score >= 32:
            grade = "A"
        elif total_score >= 28:
            grade = "B"
        elif total_score >= 21:
            grade = "C"
        elif total_score >= 14:
            grade = "D"
        else:
            grade = "F"

    # Build reason from notes
    reason = trade.get("notes", "")
    if not reason:
        reason = f"Trade #{trade['trade_num']}: {trade['title']}"

    # Decision date
    decision_date = trade.get("date", "2026-04-19")
    if not decision_date:
        decision_date = "2026-04-19"

    # Build the record
    record = {
        "decision_id": make_decision_id(trade["trade_num"]),
        "ticker": ticker,
        "company_name": company_name,
        "market": market,
        "action": action,
        "shares": trade.get("shares") or 0,
        "price": trade.get("price") or 0.0,
        "amount": amount,
        "currency": currency,
        "reason": reason,
        "thesis": "",
        "catalyst": "",
        "risk_note": "",
        "dimension_scores": json.dumps(dim_scores, ensure_ascii=False) if dim_scores else None,
        "total_score": total_score,
        "grade": grade,
        "signal": "",
        "signal_id": "",
        "portfolio_pct": 0.0,
        "expected_price_6m": 0.0,
        "expected_price_12m": 0.0,
        "expected_reasoning": "",
        "actual_price_6m": 0.0,
        "actual_price_12m": 0.0,
        "actual_return_pct": actual_return_pct if actual_return_pct is not None else 0.0,
        "review_notes": "",
        "lessons": "",
        "decision_date": decision_date,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    return record


def main():
    print("=" * 60)
    print("Trade Log → Decision Log Migration")
    print("=" * 60)

    # Load company scores
    print("\n[1] Loading company dimension scores from knowledge files...")
    company_scores = load_company_scores()
    print(f"    Loaded scores for {len(company_scores)} tickers: {list(company_scores.keys())}")

    # Parse trade log
    print("\n[2] Parsing trade-log.md...")
    trades = parse_trade_log(TRADE_LOG)
    print(f"    Found {len(trades)} trades")

    # Build records
    print("\n[3] Building decision records...")
    records = []
    for trade in trades:
        record = build_decision_record(trade, company_scores)
        records.append(record)

    # Summary before insert
    buy_count = sum(1 for r in records if r["action"] == "BUY")
    sell_count = sum(1 for r in records if r["action"] == "SELL")
    open_count = sum(1 for r in records if r["status"] == "open")
    closed_count = sum(1 for r in records if r["status"] == "closed")
    with_scores = sum(1 for r in records if r["total_score"] > 0)

    print(f"    BUY: {buy_count}, SELL: {sell_count}")
    print(f"    OPEN: {open_count}, CLOSED: {closed_count}")
    print(f"    With dimension_scores: {with_scores}")

    # Insert into DuckDB
    print("\n[4] Inserting into decision_log...")
    conn = duckdb.connect(DB_PATH)

    # Check existing
    existing = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
    print(f"    Existing rows: {existing}")

    # Delete any rows with our trade-log decision_ids to avoid duplicates
    our_ids = [r["decision_id"] for r in records]
    placeholders = ",".join(["?" for _ in our_ids])
    result = conn.execute(
        f"DELETE FROM decision_log WHERE decision_id IN ({placeholders})", our_ids
    )
    deleted_count = 0
    try:
        r = result.fetchone()
        if r:
            deleted_count = r[0]
    except Exception:
        pass
    if deleted_count:
        print(f"    Deleted {deleted_count} existing trade-log rows")

    # Insert new records
    cols = list(records[0].keys())
    col_str = ",".join(cols)
    placeholders = ",".join(["?" for _ in cols])

    for r in records:
        vals = []
        for c in cols:
            v = r[c]
            if v is None:
                vals.append(None)
            else:
                vals.append(v)
        conn.execute(
            f"INSERT INTO decision_log ({col_str}) VALUES ({placeholders})", vals
        )

    new_count = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
    print(f"    Inserted {len(records)} rows. Total now: {new_count}")

    # Print summary table
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"{'#':<5} {'Ticker':<12} {'Action':<6} {'Shares':<8} {'Price':<10} {'Status':<8} {'P/L%':<8} {'Scores'}")
    print("-" * 75)
    for r in records:
        pl_str = f"{r['actual_return_pct']:+.1f}%" if r["actual_return_pct"] else "-"
        score_str = f"{r['total_score']}/35" if r["total_score"] > 0 else "-"
        print(
            f"{r['decision_id']:<5} {r['ticker']:<12} {r['action']:<6} {r['shares']:<8} "
            f"{r['price']:<10.2f} {r['status']:<8} {pl_str:<8} {score_str}"
        )

    conn.close()
    print(f"\n✅ Migration complete: {len(records)} trades → decision_log")


if __name__ == "__main__":
    main()
