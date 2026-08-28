"""分红追踪模块。

功能：
  1. 加载/保存持仓分红数据
  2. 计算分红收入（按币种汇总）
  3. 查询指定时间段内的分红事件
  4. 生成分红日历报告
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional


DATA_FILE = Path(__file__).parent.parent.parent / "data" / "dividends.json"


def load_data() -> dict:
    """加载分红数据。"""
    if not DATA_FILE.exists():
        return {"metadata": {}, "holdings": {}, "fx_rates": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    """保存分红数据。"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["metadata"]["last_updated"] = date.today().isoformat()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_dividend(
    ticker: str,
    ex_date: str,
    amount: float,
    currency: str = "HKD",
    div_type: str = "final",
    year: str = "",
    note: str = "",
) -> None:
    """为指定公司添加一条分红记录。

    Args:
        ticker: 股票代码 (如 "01810.HK")
        ex_date: 除净日 (YYYY-MM-DD)
        amount: 每股股息
        currency: 币种 (HKD/USD/AUD/CNY)
        div_type: 类型 (final/interim/special/distribution)
        year: 财年 (如 "FY2025")
        note: 备注
    """
    data = load_data()
    holdings = data.get("holdings", {})

    if ticker not in holdings:
        print(f"⚠ {ticker} 不在持仓中，请先添加到 dividends.json")
        return

    divs = holdings[ticker].get("dividends", [])
    # 检查是否已存在（同日期+同金额）
    for d in divs:
        if d["ex_date"] == ex_date and d["amount"] == amount:
            print(f"ℹ {ticker} {ex_date} {amount} 已存在，跳过")
            return

    entry = {
        "ex_date": ex_date,
        "amount": amount,
        "currency": currency,
        "type": div_type,
    }
    if year:
        entry["year"] = year
    if note:
        entry["note"] = note

    divs.append(entry)
    # 按日期排序
    divs.sort(key=lambda d: d["ex_date"])
    holdings[ticker]["dividends"] = divs
    data["holdings"] = holdings
    save_data(data)
    print(f"✅ 已记录 {holdings[ticker]['name']}({ticker}) {ex_date} {currency} {amount}/股")


def get_dividends_in_range(
    start_date: str,
    end_date: str,
) -> list[dict]:
    """查询指定时间段内的分红事件。

    Returns:
        list of dict, 每个包含 ticker, name, shares, ex_date, amount,
        currency, total_amount, hkd_equivalent
    """
    data = load_data()
    holdings = data.get("holdings", {})
    fx = data.get("fx_rates", {})
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    results = []
    for ticker, info in holdings.items():
        shares = info.get("shares", 0)
        name = info.get("name", ticker)
        for div in info.get("dividends", []):
            ex = date.fromisoformat(div["ex_date"])
            if start <= ex <= end:
                amount = div["amount"]
                currency = div.get("currency", "HKD")
                total = amount * shares
                # 换算港币
                hkd_total = _to_hkd(total, currency, fx)
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "shares": shares,
                    "ex_date": div["ex_date"],
                    "amount": amount,
                    "currency": currency,
                    "type": div.get("type", ""),
                    "total_amount": total,
                    "hkd_equivalent": hkd_total,
                })

    results.sort(key=lambda r: r["ex_date"])
    return results


def _to_hkd(amount: float, currency: str, fx: dict) -> float:
    """将金额换算为港币。"""
    if currency == "HKD":
        return amount
    rate_key = f"{currency}_HKD"
    rate = fx.get(rate_key)
    if rate:
        return amount * rate
    return amount  # 无法换算时原样返回


def get_upcoming_dividends(days: int = 60) -> list[dict]:
    """获取未来N天内的分红事件。"""
    today = date.today()
    from datetime import timedelta
    end = today + timedelta(days=days)
    return get_dividends_in_range(today.isoformat(), end.isoformat())


def get_annual_summary(year: int = 2026) -> dict:
    """汇总某年度的分红收入。

    Returns:
        dict with per-ticker and total summaries
    """
    data = load_data()
    holdings = data.get("holdings", {})
    fx = data.get("fx_rates", {})

    summary = {}
    total_hkd = 0

    for ticker, info in holdings.items():
        shares = info.get("shares", 0)
        name = info.get("name", ticker)
        ticker_total = 0
        ticker_hkd = 0
        div_count = 0

        for div in info.get("dividends", []):
            ex = date.fromisoformat(div["ex_date"])
            if ex.year == year:
                amount = div["amount"]
                currency = div.get("currency", "HKD")
                total = amount * shares
                hkd = _to_hkd(total, currency, fx)
                ticker_total += total
                ticker_hkd += hkd
                div_count += 1

        if div_count > 0:
            summary[ticker] = {
                "name": name,
                "shares": shares,
                "div_count": div_count,
                "total_amount": ticker_total,
                "currency": info.get("currency", "HKD"),
                "hkd_equivalent": ticker_hkd,
            }
            total_hkd += ticker_hkd

    return {"year": year, "tickers": summary, "total_hkd": total_hkd}


def format_calendar_report(start_date: str, end_date: str) -> str:
    """生成分红日历报告（纯文本）。"""
    divs = get_dividends_in_range(start_date, end_date)
    if not divs:
        return f"📅 {start_date} ~ {end_date} 期间无分红事件"

    lines = []
    lines.append(f"📅 持仓分红日历 ({start_date} ~ {end_date})")
    lines.append("=" * 60)

    # 按币种分组汇总
    by_currency: dict[str, float] = {}

    for d in divs:
        cur = d["currency"]
        total = d["total_amount"]
        by_currency[cur] = by_currency.get(cur, 0) + total

        lines.append(
            f"  {d['ex_date']}  {d['name']:<8}({d['ticker']:<10})  "
            f"{d['currency']} {d['amount']:.4f}/股 × {d['shares']:,}股 = "
            f"{d['currency']} {total:,.2f}"
        )

    lines.append("-" * 60)
    lines.append("  合计:")
    for cur, total in sorted(by_currency.items()):
        lines.append(f"    {cur} {total:,.2f}")

    return "\n".join(lines)
