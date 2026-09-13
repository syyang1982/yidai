#!/usr/bin/env python3
"""
P0: 从 trade-log.md 补录历史交易到 DecisionLog

解析 trade-log.md 的42条交易，结合公司分析文件的七维评分，
写入 decision.py 的 DecisionLog (DuckDB)。

用法:
    cd ~/.hermes/yidai
    python scripts/backfill_decisions.py              # 试运行
    python scripts/backfill_decisions.py --apply       # 实际写入
"""

from __future__ import annotations

import re
import sys
import json
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy.decision import DecisionLog, DecisionRecord

TRADE_LOG_PATH = Path.home() / ".hermes" / "trading" / "trade-log.md"
COMPANIES_DIR = PROJECT_ROOT / "knowledge" / "companies"
DEFAULT_DB = PROJECT_ROOT / "db" / "decisions.duckdb"

# ticker 标准化映射
TICKER_NORMALIZE = {
    "1810.HK": "01810.HK",
    "2020.HK": "02020.HK",
    "2252.HK": "02252.HK",
    "2498.HK": "02498.HK",
    "3888.HK": "03888.HK",
    "3896.HK": "03896.HK",
    "9626.HK": "09626.HK",
    "9896.HK": "09896.HK",
    "9999.HK": "09999.HK",
    "09988.HK": "09988.HK",
    "1361.HK": "1361.HK",
    "600036.SH": "600036.SH",
}

TICKER_MAP = {
    "LX": ("LexinFintech", "US", "LX"),
    "Xiaomi": ("小米集团", "HK", "01810.HK"),
    "小米": ("小米集团", "HK", "01810.HK"),
    "ANTA": ("安踏体育", "HK", "02020.HK"),
    "安踏": ("安踏体育", "HK", "02020.HK"),
    "Weimob": ("微创机器人", "HK", "02252.HK"),
    "Medbot": ("微创机器人", "HK", "02252.HK"),
    "微创": ("微创机器人", "HK", "02252.HK"),
    "RoboSense": ("速腾聚创", "HK", "02498.HK"),
    "速腾": ("速腾聚创", "HK", "02498.HK"),
    "Kingsoft SW": ("金山软件", "HK", "03888.HK"),
    "金山软件": ("金山软件", "HK", "03888.HK"),
    "Kingsoft Cloud": ("金山云", "HK", "03896.HK"),
    "金山云": ("金山云", "HK", "03896.HK"),
    "Bilibili": ("哔哩哔哩", "HK", "09626.HK"),
    "B站": ("哔哩哔哩", "HK", "09626.HK"),
    "MINISO": ("名创优品", "HK", "09896.HK"),
    "名创": ("名创优品", "HK", "09896.HK"),
    "NetEase": ("网易", "HK", "09999.HK"),
    "网易": ("网易", "HK", "09999.HK"),
    "Alibaba": ("阿里巴巴", "HK", "09988.HK"),
    "阿里": ("阿里巴巴", "HK", "09988.HK"),
    "Stockland": ("Stockland", "AU", "SGP.AX"),
    "361": ("361度", "HK", "1361.HK"),
    "361度": ("361度", "HK", "1361.HK"),
    "361 Degrees": ("361度", "HK", "1361.HK"),
    "China Merchants Bank": ("招商银行", "A", "600036.SH"),
    "招行": ("招商银行", "A", "600036.SH"),
    "招商银行": ("招商银行", "A", "600036.SH"),
}

CURRENCY_MAP = {"HK": "HKD", "A": "CNY", "US": "USD", "AU": "AUD"}


def load_company_scores(ticker: str) -> dict:
    """从公司分析文件加载七维评分。"""
    # 尝试多种文件名格式
    candidates = [
        COMPANIES_DIR / f"{ticker}.md",
        COMPANIES_DIR / f"{ticker.replace('.HK', '')}.HK.md",
    ]
    # 标准化
    norm = TICKER_NORMALIZE.get(ticker, ticker)
    candidates.append(COMPANIES_DIR / f"{norm}.md")

    for path in candidates:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            scores = {}
            dim_names = ["盈利", "健康", "现金流", "估值", "成长", "股东", "战略"]
            for dim in dim_names:
                # 匹配表格格式: | 现金流 | 5/5 | 或 | 现金流 | 5 |
                m = re.search(rf'\|\s*{dim}\s*\|\s*(\d+)(?:/\d+)?\s*\|', text)
                if not m:
                    # 匹配 key: value 格式
                    m = re.search(rf'{dim}\s*[:：]\s*(\d+)', text)
                if m:
                    val = int(m.group(1))
                    if 1 <= val <= 5:
                        scores[dim] = val
            if scores:
                return scores
    return {}


def infer_reason_and_thesis(trade: dict) -> tuple[str, str, str, str]:
    """从交易条目推断 reason/thesis/catalyst/risk_note。"""
    notes = trade.get("notes", "")
    raw_action = trade.get("action", "")
    action = action_type(raw_action)

    # 根据 action 和 notes 推断
    is_buy = action in ("BUY", "ADD")
    is_sell = action in ("SELL", "REDUCE")

    if "获利了结" in notes or "profit-taking" in notes.lower():
        reason = "获利了结"
        thesis = notes
        catalyst = "价格达到获利目标"
    elif is_sell and ("减仓" in notes or "partial" in notes.lower()):
        reason = "部分减仓获利"
        thesis = notes
        catalyst = "价格达到部分获利目标"
    elif is_sell and ("清仓" in notes or "全部卖出" in notes or "FULL EXIT" in notes):
        reason = "清仓退出"
        thesis = notes
        catalyst = "止损/策略调整"
    elif is_sell and "释放资金" in notes:
        reason = "减仓释放资金"
        thesis = notes
        catalyst = "资金再平衡"
    elif is_sell:
        reason = "卖出"
        thesis = notes
        catalyst = ""
    elif "补仓" in notes or "加仓" in notes or "avg-down" in notes.lower() or "averaging down" in notes.lower():
        reason = "低位加仓摊低成本"
        thesis = notes
        catalyst = "价格回调至支撑位"
    elif "回补" in notes:
        reason = "低位回补"
        thesis = notes
        catalyst = "价格回调后重新建仓"
    elif "swing" in notes.lower() or "波段" in notes:
        reason = "短线波段交易"
        thesis = notes
        catalyst = "技术面短线机会"
    elif "diversif" in notes.lower() or "分散" in notes:
        reason = "分散投资建仓"
        thesis = notes
        catalyst = "组合多元化"
    elif is_buy and ("core" in notes.lower() or "核心" in notes or "长期" in notes):
        reason = "核心仓位建仓"
        thesis = notes
        catalyst = "看好公司长期基本面"
    elif is_buy:
        reason = "建仓/加仓"
        thesis = notes
        catalyst = "看好公司基本面"
    else:
        reason = notes[:80] if notes else "未记录"
        thesis = notes
        catalyst = ""

    # 风险提示
    risk = ""
    if "dead money" in notes.lower() or "-70" in notes or "-80" in notes:
        risk = "深度套牢，已成死钱"
    elif "stop-loss" in notes.lower() or "止损" in notes:
        risk = "触及止损线"
    elif "underwater" in notes.lower() or "套牢" in notes:
        risk = "账面亏损"

    return reason, thesis, catalyst, risk


def determine_signal(scores: dict, action: str) -> str:
    """根据评分和操作推断信号。"""
    if not scores:
        return "WATCH"
    total = sum(scores.values())
    if action in ("BUY", "ADD") and total >= 25:
        return "BUY"
    elif action in ("SELL", "REDUCE"):
        return "REDUCE"
    elif total >= 25:
        return "BUY"
    elif total >= 18:
        return "HOLD"
    else:
        return "WATCH"


def parse_trade_log(path: Path) -> list[dict]:
    """解析 trade-log.md，返回交易条目列表。"""
    text = path.read_text(encoding="utf-8")
    trades = []

    # 匹配 ### Trade #XXX — Name (Ticker) 或 ### Trade #XXX — Name
    header_pattern = re.compile(
        r"###\s+Trade\s+#(\d+)\s+—\s+(.+?)$",
        re.MULTILINE,
    )

    headers = list(header_pattern.finditer(text))

    for i, match in enumerate(headers):
        trade_num = int(match.group(1))
        name_ticker_str = match.group(2).strip()

        # 提取 name 和 ticker
        tm = re.match(r"(.+?)\s*\((.+?)\)", name_ticker_str)
        if tm:
            name = tm.group(1).strip()
            ticker_raw = tm.group(2).strip()
        else:
            name = name_ticker_str
            ticker_raw = ""

        # 提取该 trade 的文本块
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]

        # 解析字段
        trade = {
            "num": trade_num,
            "name": name,
            "ticker_raw": ticker_raw,
            "block": block,
        }

        for field_name, pattern in [
            ("action", r"Action:\s*(.+)"),
            ("date", r"Date:\s*(.+)"),
            ("status", r"Status:\s*(.+)"),
            ("current", r"Current:\s*(.+)"),
            ("pnl", r"P/L:\s*(.+)"),
            ("notes", r"Notes:\s*(.+)"),
            ("realized_gain", r"Realized gain:\s*(.+)"),
            ("realized_loss", r"Realized loss:\s*(.+)"),
        ]:
            m = re.search(pattern, block)
            if m:
                trade[field_name] = m.group(1).strip()

        trades.append(trade)

    return trades


def resolve_ticker(trade: dict) -> tuple[str, str, str]:
    """返回 (company_name, market, normalized_ticker)。"""
    name = trade.get("name", "")
    ticker_raw = trade.get("ticker_raw", "")

    # 先用 ticker_raw 查
    if ticker_raw in TICKER_MAP:
        return TICKER_MAP[ticker_raw]
    # 尝试标准化
    norm = TICKER_NORMALIZE.get(ticker_raw, ticker_raw)
    for key, val in TICKER_MAP.items():
        if val[2] == norm:
            return val

    # 用 name 查
    for key, val in TICKER_MAP.items():
        if key.lower() in name.lower():
            return val

    return (name, "HK", ticker_raw)


def parse_price_and_shares(trade: dict) -> tuple[float, int, str]:
    """从 action 字段解析价格和股数。"""
    action = trade.get("action", "")

    # 解析股数
    shares_m = re.search(r"([\d,]+)\s*shares?", action, re.IGNORECASE)
    shares = int(shares_m.group(1).replace(",", "")) if shares_m else 0

    # 解析价格 — 支持多种格式
    price = 0.0
    currency = "HKD"

    # HK$X.XX / US$X.XX / A$X.XX / CNY X.XX
    price_m = re.search(r"(?:HK\$|US\$|A\$|CNY\s*)([\d.]+)", action)
    if price_m:
        price = float(price_m.group(1))
        if "US$" in action:
            currency = "USD"
        elif "A$" in action:
            currency = "AUD"
        elif "CNY" in action:
            currency = "CNY"
        else:
            currency = "HKD"

    return price, shares, currency


def parse_date(date_str: str) -> str:
    """解析日期字符串为 ISO 格式。"""
    if not date_str:
        return date.today().isoformat()

    # 清理
    date_str = date_str.strip().rstrip(".")

    # 尝试多种格式
    # 范围日期，取第一个
    range_m = re.match(r"(\d{4}-\d{2}-\d{2})\s+to\s+\d{4}-\d{2}-\d{2}", date_str)
    if range_m:
        return range_m.group(1)

    for fmt in [
        "%Y-%m-%d",
        "%Y-%m-%d (%a)",
        "%B %d, %Y",
        "%b %d, %Y",
    ]:
        try:
            return datetime.strptime(date_str, fmt).date().isoformat()
        except ValueError:
            continue

    # 尝试提取第一个日期
    m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
    if m:
        return m.group(1)

    # "est" 后缀
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*\(est\)", date_str)
    if m:
        return m.group(1)

    return date.today().isoformat()


def action_type(raw_action: str) -> str:
    """推断标准化 action 类型。"""
    a = raw_action.upper()
    # 提取股数用于判断
    shares_m = re.search(r"([\d,]+)\s*shares?", raw_action, re.IGNORECASE)
    shares = int(shares_m.group(1).replace(",", "")) if shares_m else 0

    if "SELL" in a:
        # PARTIAL SELL 或小量卖出视为 REDUCE
        if "PARTIAL" in a or (0 < shares <= 2000):
            return "REDUCE"
        return "SELL"
    if "BUY" in a:
        if any(k in raw_action for k in ["Add", "add", "RE-BUY", "Re-buy", "re-buy"]):
            return "ADD"
        return "BUY"
    return "HOLD"


def main():
    apply = "--apply" in sys.argv
    db_path = DEFAULT_DB

    for arg in sys.argv[1:]:
        if arg.startswith("--db="):
            db_path = Path(arg.split("=", 1)[1])

    print(f"解析 trade-log.md ...")
    trades = parse_trade_log(TRADE_LOG_PATH)
    print(f"找到 {len(trades)} 条交易记录\n")

    if not apply:
        print("=== 试运行模式 (加 --apply 实际写入) ===\n")

    # 加载公司评分缓存
    score_cache: dict[str, dict] = {}

    dl = DecisionLog(str(db_path) if apply else ":memory:")
    records = []

    for trade in trades:
        company_name, market, ticker = resolve_ticker(trade)
        price, shares, currency = parse_price_and_shares(trade)
        trade_date = parse_date(trade.get("date", ""))
        action_raw = trade.get("action", "")
        action = action_type(action_raw)
        notes = trade.get("notes", "")

        # 加载公司评分
        if ticker not in score_cache:
            score_cache[ticker] = load_company_scores(ticker)
        scores = score_cache.get(ticker, {})

        # 推断决策上下文
        reason, thesis, catalyst, risk = infer_reason_and_thesis(trade)
        signal = determine_signal(scores, action)

        rec = DecisionRecord(
            ticker=ticker,
            company_name=company_name,
            market=market,
            action=action,
            shares=shares,
            price=price,
            amount=shares * price if shares and price else 0,
            currency=currency,
            reason=reason,
            thesis=thesis,
            catalyst=catalyst,
            risk_note=risk,
            dimension_scores=scores,
            total_score=sum(scores.values()) if scores else 0,
            grade="",  # 后续根据总分计算
            signal=signal,
            decision_date=trade_date,
            status="active",
        )

        # 计算 grade
        if rec.total_score >= 28:
            rec.grade = "A"
        elif rec.total_score >= 21:
            rec.grade = "B"
        elif rec.total_score >= 14:
            rec.grade = "C"
        elif rec.total_score >= 8:
            rec.grade = "D"
        elif rec.total_score > 0:
            rec.grade = "F"

        records.append(rec)

        # 打印预览
        scores_str = json.dumps(scores, ensure_ascii=False) if scores else "无"
        print(f"  #{trade['num']:03d} | {trade_date} | {action:6s} | {company_name:8s} ({ticker}) | "
              f"{shares}股 @ {price} {currency} | 评分: {rec.total_score or 'N/A'} ({rec.grade or '-'}) | "
              f"评分来源: {scores_str}")
        print(f"       理由: {reason}")

    print(f"\n共 {len(records)} 条决策记录待写入")

    if not apply:
        print("\n提示: 运行 python scripts/backfill_decisions.py --apply 实际写入")
        print(f"目标数据库: {db_path}")
        return

    # 写入
    print(f"\n写入 {db_path} ...")
    dl = DecisionLog(str(db_path))
    accepted = 0
    warnings_total = 0
    for rec in records:
        result = dl.record(rec, enforce_constraints=False)
        if result["accepted"]:
            accepted += 1
        if result["warnings"]:
            warnings_total += len(result["warnings"])
            for w in result["warnings"]:
                print(f"  ⚠️ {rec.ticker}: {w}")

    # 统计
    stats = dl.get_stats()
    print(f"\n写入完成:")
    print(f"  成功: {accepted}/{len(records)}")
    print(f"  警告: {warnings_total}")
    print(f"  数据库总决策数: {stats['total_decisions']}")
    print(f"  按操作分布: {stats['by_action']}")


if __name__ == "__main__":
    main()
