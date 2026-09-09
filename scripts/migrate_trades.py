"""
W2.1.3 — 从 trade-log.md 迁移交易记录到结构化决策日志

解析 ~/.hermes/trading/trade-log.md 中的交易条目，
转换为 DecisionRecord 格式并写入 yidai DuckDB。

用法:
    cd ~/.hermes/yidai
    python scripts/migrate_trades.py              # 试运行(不写入)
    python scripts/migrate_trades.py --apply       # 实际写入
    python scripts/migrate_trades.py --apply --db db/decisions.duckdb  # 指定DB
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy.decision import DecisionLog, DecisionRecord

TRADE_LOG_PATH = Path.home() / ".hermes" / "trading" / "trade-log.md"
DEFAULT_DB = PROJECT_ROOT / "db" / "decisions.duckdb"

# ticker → (company_name, market) 映射
TICKER_MAP = {
    "LX": ("LexinFintech", "US"),
    "1810.HK": ("小米集团", "HK"),
    "2020.HK": ("安踏体育", "HK"),
    "2252.HK": ("微创机器人", "HK"),
    "2498.HK": ("速腾聚创", "HK"),
    "3888.HK": ("金山软件", "HK"),
    "3896.HK": ("金山云", "HK"),
    "9626.HK": ("哔哩哔哩", "HK"),
    "9896.HK": ("名创优品", "HK"),
    "9999.HK": ("网易", "HK"),
    "09988.HK": ("阿里巴巴", "HK"),
    "SGP.AX": ("Stockland", "AU"),
    "1361.HK": ("361度", "HK"),
    "600036.SH": ("招商银行", "A"),
}

# 货币推断
CURRENCY_MAP = {
    "HK": "HKD", "A": "CNY", "US": "USD", "AU": "AUD",
}

# 名称 → ticker 反向映射
NAME_TICKER_MAP = {
    "LX": "LX", "LexinFintech": "LX",
    "Xiaomi": "1810.HK", "小米": "1810.HK",
    "ANTA": "2020.HK", "ANTA Sports": "2020.HK", "安踏": "2020.HK",
    "Weimob": "2252.HK", "Medbot": "2252.HK", "微创": "2252.HK",
    "RoboSense": "2498.HK", "速腾": "2498.HK",
    "Kingsoft SW": "3888.HK", "金山软件": "3888.HK",
    "Kingsoft Cloud": "3896.HK", "金山云": "3896.HK",
    "Bilibili": "9626.HK", "B站": "9626.HK",
    "MINISO": "9896.HK", "名创": "9896.HK",
    "NetEase": "9999.HK", "网易": "9999.HK",
    "Alibaba": "09988.HK", "阿里": "09988.HK",
    "Stockland": "SGP.AX",
    "361": "1361.HK", "361度": "1361.HK", "361 Degrees": "1361.HK",
    "China Merchants Bank": "600036.SH", "招行": "600036.SH", "招商银行": "600036.SH",
}


def parse_trade_log(path: Path) -> list[dict]:
    """解析 trade-log.md，返回原始交易条目列表。"""
    text = path.read_text(encoding="utf-8")
    trades = []

    # 匹配 ### Trade #XXX — Name (Ticker) 或类似格式
    pattern = re.compile(
        r"###\s+Trade\s+#(\d+)\s+—\s+(.+?)$",
        re.MULTILINE,
    )

    for match in pattern.finditer(text):
        trade_num = int(match.group(1))
        title = match.group(2).strip()

        # 提取该条目到下一个 ### 或 ---
        start = match.end()
        next_section = re.search(r"\n###|\n---", text[start:])
        end = start + next_section.start() if next_section else len(text)
        body = text[start:end]

        # 解析字段
        trade = {
            "trade_num": trade_num,
            "title": title,
            "body": body,
        }

        # 提取 Action
        action_match = re.search(r"- Action:\s*(.+)", body)
        if action_match:
            trade["action_raw"] = action_match.group(1).strip()

        # 提取 Date
        date_match = re.search(r"- Date:\s*(.+)", body)
        if date_match:
            trade["date_raw"] = date_match.group(1).strip()

        # 提取 Status
        status_match = re.search(r"- Status:\s*(.+)", body)
        if status_match:
            trade["status_raw"] = status_match.group(1).strip()

        # 提取 Notes
        notes_match = re.search(r"- Notes:\s*(.+)", body)
        if notes_match:
            trade["notes"] = notes_match.group(1).strip()

        # 提取 P/L
        pl_match = re.search(r"- P/L:\s*(.+)", body)
        if pl_match:
            trade["pl_raw"] = pl_match.group(1).strip()

        # 提取 Realized
        realized_match = re.search(r"- Realized (?:gain|P/L|loss):\s*(.+)", body)
        if realized_match:
            trade["realized"] = realized_match.group(1).strip()

        trades.append(trade)

    return trades


def resolve_ticker(title: str) -> str | None:
    """从标题中推断 ticker。"""
    # 尝试从括号中提取 ticker
    ticker_match = re.search(r"\(([A-Za-z0-9.]+(?:\.HK|\.SH|\.SZ|\.AX|\.SS)?)\)", title)
    if ticker_match:
        code = ticker_match.group(1)
        # 如果是纯数字且5位，加上.HK
        if code.isdigit() and len(code) == 5:
            code = code.lstrip("0") or "0"
            return f"{code}.HK"
        # 检查已知 ticker
        for key in TICKER_MAP:
            if code in key or key in code:
                return key
        return code

    # 尝试名称匹配
    for name, ticker in NAME_TICKER_MAP.items():
        if name.lower() in title.lower():
            return ticker
    return None


def parse_action(action_raw: str) -> tuple[str, int, float, str]:
    """从 action_raw 解析 (action, shares, price, currency)。

    格式示例:
        BUY 1,800 shares @ USD$6.29
        BUY 23,600 shares @ HK$23.19
        SELL 400 shares @ HK$68.35
        BUY 500 shares @ CNY8.948 (~HK$10.25)
        BUY 700 shares @ CNY36.109
        SELL 100 shares @ HK$125.30
        BUY 300 shares @ CNY35.57 (6/30) -> SELL 300 shares @ CNY36.82 (7/3)
    """
    action = "BUY"
    shares = 0
    price = 0.0
    currency = "HKD"

    # 判断买入/卖出
    upper = action_raw.upper()
    if "SELL" in upper.split()[0] or upper.startswith("SELL"):
        action = "SELL"
    elif "BUY" in upper.split()[0] or upper.startswith("BUY"):
        action = "BUY"
    elif "ADD" in upper:
        action = "ADD"
    elif "REDUCE" in upper:
        action = "REDUCE"

    # 提取第一个 BUY/SELL 的数据（忽略 RE-BUY 复杂格式）
    # 匹配: BUY 1,800 shares @ USD$6.29 或 BUY 23,600 shares @ HK$23.19
    buy_sell = re.search(
        r"(?:BUY|SELL)\s+([\d,]+)\s+shares?\s+@\s+(?:([A-Z]{2,3})\$?)?([\d.]+)",
        action_raw,
    )
    if buy_sell:
        shares = int(buy_sell.group(1).replace(",", ""))
        cur = buy_sell.group(2)
        price = float(buy_sell.group(3))
        if cur:
            currency = cur

    return action, shares, price, currency


def parse_date(date_raw: str) -> str:
    """提取日期，返回 YYYY-MM-DD 格式。"""
    # 匹配 2026-04-19 格式
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_raw)
    if iso_match:
        return iso_match.group(1)

    # 匹配 2026/04/19 格式
    slash_match = re.search(r"(\d{4}/\d{2}/\d{2})", date_raw)
    if slash_match:
        return slash_match.group(1).replace("/", "-")

    return ""


def convert_to_decision(trade: dict) -> DecisionRecord | None:
    """将原始交易条目转换为 DecisionRecord。"""
    ticker = resolve_ticker(trade.get("title", ""))
    if not ticker:
        return None

    company_name, market = TICKER_MAP.get(ticker, (trade.get("title", ""), ""))
    currency = CURRENCY_MAP.get(market, "HKD")

    action_raw = trade.get("action_raw", "")
    if not action_raw:
        return None

    action, shares, price, cur = parse_action(action_raw)
    if cur:
        currency = cur

    # SC 买入的用 CNY
    body = trade.get("body", "")
    if "SC" in body or "Stock Connect" in body:
        if market == "A":
            currency = "CNY"
        # SC 买港股有时用 CNY
        if "CNY" in action_raw:
            currency = "CNY"

    # 对于 SC 港股买入（CNY），需要转换为 HKD 用于 amount 计算
    # 但 DecisionRecord 保持原始货币
    amount = shares * price

    decision_date = parse_date(trade.get("date_raw", ""))

    # 推断 action type
    action_type = action
    if action == "BUY" and "batch" in trade.get("title", "").lower():
        action_type = "ADD"
    if action == "BUY" and "add" in trade.get("title", "").lower():
        action_type = "ADD"
    if action == "SELL" and "partial" in trade.get("title", "").lower():
        action_type = "REDUCE"

    rec = DecisionRecord(
        ticker=ticker,
        company_name=company_name,
        market=market,
        action=action_type,
        shares=shares,
        price=price,
        amount=amount,
        currency=currency,
        reason=trade.get("notes", ""),
        decision_date=decision_date,
        status="closed" if "CLOSED" in trade.get("status_raw", "") else "active",
    )

    return rec


def migrate(trade_log_path: Path = TRADE_LOG_PATH, db_path: Path = DEFAULT_DB, apply: bool = False):
    """执行迁移。"""
    print(f"解析 {trade_log_path} ...")
    trades = parse_trade_log(trade_log_path)
    print(f"找到 {len(trades)} 条交易记录\n")

    # 转换
    records: list[DecisionRecord] = []
    skipped: list[tuple[int, str]] = []

    for trade in trades:
        rec = convert_to_decision(trade)
        if rec:
            # 使用 trade_num 作为 decision_id 前缀
            rec.decision_id = f"TL-{trade['trade_num']:03d}"
            records.append(rec)
        else:
            skipped.append((trade["trade_num"], trade["title"]))

    print(f"成功转换: {len(records)} 条")
    print(f"跳过: {len(skipped)} 条")
    if skipped:
        print("  跳过的条目:")
        for num, title in skipped:
            print(f"    #{num}: {title}")

    # 打印摘要
    print(f"\n{'='*60}")
    print(f"  迁移预览")
    print(f"{'='*60}")
    for rec in records[:10]:
        print(f"  {rec.decision_id} | {rec.decision_date} | {rec.action:5s} | "
              f"{rec.ticker:12s} | {rec.shares:>6d}股 @ {rec.currency}{rec.price:.2f}")
    if len(records) > 10:
        print(f"  ... 还有 {len(records)-10} 条")

    if not apply:
        print(f"\n[试运行] 使用 --apply 参数实际写入 {db_path}")
        return

    # 写入
    print(f"\n写入 {db_path} ...")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    log = DecisionLog(str(db_path))

    success = 0
    failed = 0
    for rec in records:
        result = log.record(rec, enforce_constraints=False)
        if result["accepted"]:
            success += 1
        else:
            failed += 1
            print(f"  写入失败 {rec.decision_id}: {result['violations']}")

    print(f"\n完成: {success} 成功, {failed} 失败")

    # 验证
    stats = log.get_stats()
    print(f"数据库统计: {stats}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="迁移 trade-log.md 到决策日志")
    parser.add_argument("--apply", action="store_true", help="实际写入(默认仅预览)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="DuckDB 路径")
    parser.add_argument("--trade-log", default=str(TRADE_LOG_PATH), help="trade-log.md 路径")
    args = parser.parse_args()

    migrate(
        trade_log_path=Path(args.trade_log),
        db_path=Path(args.db),
        apply=args.apply,
    )
