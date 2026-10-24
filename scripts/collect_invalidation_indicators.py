"""失效指标自动采集器 — 把能从财报 API 自动拿到的指标写入 leading_indicators + indicator_history。

数据源（2026-10-14 实测）：
  港股: datacenter.eastmoney.com RPT_HKF10_FN_MAININDICATOR（89字段，多期，质量高）
  美股: RPT_USF10_FN_BALANCE / RPT_USF10_FN_INCOME（逐项报表，较麻烦）
  澳股: 东财无 SGP 数据 → 需人工
  行情: query1.finance.yahoo.com/v8/finance/chart（算覆盖倍数用）

用法:
    python scripts/collect_invalidation_indicators.py [--dry-run] [--periods 6]

诚实标注：本脚本只覆盖「财报可得」的指标。月度交付、同店销售、DAU、
版号、定点数等运营指标不在财报里，仍需人工或网络检索，会在报告末尾列出。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.leading_indicators import LeadingIndicatorStore  # noqa: E402
from src.strategy.invalidation_watch import WATCH  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

# 港股 F10 主要指标 → 失效指标映射
# key: (ticker, indicator_name)  value: (API字段, 单位换算, 说明)
HK_MAP = {
    ("01810.HK", "经营现金流"):        ("NETCASH_OPERATE", 1e8, "亿元"),
    ("02252.HK", "经营现金流"):        ("NETCASH_OPERATE", 1e8, "亿元"),
    ("02498.HK", "经营现金流"):        ("NETCASH_OPERATE", 1e8, "亿元"),
    ("02020.HK", "集团毛利率"):        ("GROSS_PROFIT_RATIO", 1.0, "%"),
    ("03888.HK", "办公毛利率"):        ("GROSS_PROFIT_RATIO", 1.0, "%"),
    ("03888.HK", "办公软件收入同比"):   ("OPERATE_INCOME_YOY", 1.0, "%"),
    ("03896.HK", "经营现金流营收比"):   ("OCF_SALES", 1.0, "%"),
    ("09626.HK", "经营利润"):          ("OPERATE_PROFIT", 1e8, "亿元"),
    ("09999.HK", "游戏毛利率"):        ("GROSS_PROFIT_RATIO", 1.0, "%"),
    ("09988.HK", "云收入增速"):        (None, None, "%"),  # 分部数据，MAININDICATOR 无
}

# 需人工/网络检索的指标（诚实列出，不要假装能自动采）
MANUAL_ONLY = {
    "01810.HK": ["SU7月交付同比", "SU7月交付量"],
    "02020.HK": ["FILA增速", "始祖鸟同店增速"],
    "02252.HK": ["手术量增速"],
    "02498.HK": ["车型定点数"],
    "03896.HK": ["AI云收入增速", "大客户CapEx"],
    "09626.HK": ["DAU增速", "广告收入增速"],
    "09896.HK": ["海外同店增速", "存货周转天数", "IP授权收入占比"],
    "09988.HK": ["云收入增速", "云经分利润率", "中国零售增速"],
    "09999.HK": ["新游流水", "游戏版号获取"],
    "SGP.AX": ["住宅合同同比", "NOI增速", "净负债率"],
}


def fetch(url: str, referer: str = "https://emweb.securities.eastmoney.com/") -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_hk_main(code: str, pages: int = 1, page_size: int = 12) -> list[dict]:
    url = (
        "https://datacenter.eastmoney.com/securities/api/data/v1/get?"
        f"reportName=RPT_HKF10_FN_MAININDICATOR&columns=ALL&pageSize={page_size}"
        f"&filter=(SECUCODE%3D%22{code}.HK%22)&sortColumns=REPORT_DATE&sortTypes=-1"
        "&source=F10&client=PC"
    )
    try:
        d = fetch(url)
        return (d.get("result") or {}).get("data") or []
    except Exception as exc:  # 网络/解析失败不要炸整个采集
        print(f"  ⚠️ {code} 港股财报拉取失败: {exc}")
        return []


def fetch_yahoo_price(symbol: str) -> float | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    try:
        d = fetch(url, referer="https://finance.yahoo.com/")
        return d["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as exc:
        print(f"  ⚠️ {symbol} 行情拉取失败: {exc}")
        return None


def period_of(row: dict) -> str:
    """用报告期日期做 period，保证字符串排序 == 时间排序。"""
    rd = row.get("REPORT_DATE") or row.get("STD_REPORT_DATE") or ""
    return rd[:10]


def fetch_us_equity_items(code: str) -> tuple[dict, dict]:
    """美股逐项报表：返回 {日期: 归母权益} 和 {日期: 摊薄股数}。

    东财美股 BALANCE/INCOME 是「科目逐行」结构，且 pageSize 大了会返回损坏 JSON，
    所以按 ITEM_NAME 精确过滤，避开全量拉取。
    """
    import urllib.parse

    def grab(report: str, item: str) -> dict:
        f = urllib.parse.quote(f'(SECUCODE="{code}")(ITEM_NAME="{item}")')
        url = (
            "https://datacenter.eastmoney.com/securities/api/data/v1/get?"
            f"reportName={report}&columns=ALL&pageSize=200&filter={f}"
            "&sortColumns=REPORT_DATE&sortTypes=-1&source=F10&client=PC"
        )
        try:
            raw = fetch(url)["result"]["data"]
        except Exception as exc:
            print(f"  ⚠️ {code} {item} 拉取失败: {exc}")
            return {}
        out: dict[str, float] = {}
        for x in raw or []:
            d = (x.get("REPORT_DATE") or "")[:10]
            if d and x.get("AMOUNT") is not None:
                out[d] = max(out.get(d, 0.0), float(x["AMOUNT"]))
        return out

    equity = grab("RPT_USF10_FN_BALANCE", "归属于母公司股东权益")
    shares = grab("RPT_USF10_FN_INCOME", "摊薄加权平均股数-普通股")
    return equity, shares


def collect_us_cover_ratio(
    store: LeadingIndicatorStore, periods: int = 8, dry_run: bool = False
) -> tuple[int, list]:
    """LX 净资产覆盖倍数 = (归母权益/摊薄股数) × ADS_RATIO × CNYUSD汇率 / ADS现价。

    口径要点：乐信 1 ADS = 2 普通股，Yahoo 的 BVPS 与股价都是 ADS 口径，
    必须统一到 ADS 再相除，否则会差一倍（2026-10-14 曾误记 10.7，实为 15.5）。
    """
    ADS_RATIO = 2
    written, failed = 0, []
    equity, shares = fetch_us_equity_items("LX.O")
    if not equity or not shares:
        return 0, [("LX", "美股归母权益/股数拉取失败")]
    fx = None
    px = None
    try:
        fx = fetch(
            "https://query1.finance.yahoo.com/v8/finance/chart/CNYUSD=X?interval=1d&range=2d",
            referer="https://finance.yahoo.com/",
        )["chart"]["result"][0]["meta"]["regularMarketPrice"]
        px = fetch(
            "https://query1.finance.yahoo.com/v8/finance/chart/LX?interval=1d&range=2d",
            referer="https://finance.yahoo.com/",
        )["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as exc:
        return 0, [("LX", f"汇率/行情拉取失败: {exc}")]

    dates = sorted(equity, reverse=True)[:periods]
    latest_val = None
    latest_period = None
    for d in dates:
        if d not in shares:
            continue
        bps_ads = (equity[d] / shares[d]) * ADS_RATIO * fx
        cover = bps_ads / px
        if not dry_run:
            try:
                store.record_history("LX", "净资产覆盖倍数", d, cover)
            except Exception as exc:
                failed.append(("LX", f"{d} 写入失败: {exc}"))
                continue
        written += 1
        if latest_val is None:
            latest_val, latest_period = cover, d
    if latest_val is not None and not dry_run:
        store.update_value("LX", "净资产覆盖倍数", latest_val, latest_period)
    return written, failed


def collect(store: LeadingIndicatorStore, periods: int = 6, dry_run: bool = False) -> dict:
    stats = {"written": 0, "skipped": 0, "failed": 0, "no_data": []}
    seen = set()

    for ticker, company, specs in WATCH:
        specs_by_name = {s.name for s in specs}
        auto_specs = [n for (t, n) in HK_MAP if t == ticker and n in specs_by_name]
        if not auto_specs:
            continue
        code = ticker.split(".")[0]
        rows = fetch_hk_main(code)[:periods]
        if not rows:
            stats["no_data"].append((ticker, "港股财报 API 无数据"))
            continue

        for name in auto_specs:
            field, factor, unit = HK_MAP[(ticker, name)]
            if field is None:
                stats["no_data"].append((ticker, f"{name}（分部数据，MAININDICATOR 不含）"))
                continue
            got = 0
            for row in rows:
                v = row.get(field)
                if v is None:
                    continue
                val = float(v) / factor
                if dry_run:
                    got += 1
                    continue
                try:
                    store.record_history(ticker, name, period_of(row), val)
                    got += 1
                except Exception as exc:
                    stats["failed"] += 1
                    print(f"  ⚠️ 写入失败 {ticker}/{name}/{period_of(row)}: {exc}")
            seen.add((ticker, name))
            if got:
                stats["written"] += got
                latest = rows[0]
                if not dry_run and latest.get(field) is not None:
                    store.update_value(ticker, name, float(latest[field]) / factor, period_of(latest))
            else:
                stats["skipped"] += 1

    # LX：净资产覆盖倍数 = BPS/ADS / ADS现价（美股逐项报表，口径见 collect_us_cover_ratio）
    n, fails = collect_us_cover_ratio(store, periods=max(periods, 8), dry_run=dry_run)
    stats["written"] += n
    if n == 0:
        stats["no_data"].append(("LX", "美股归母权益/股数拉取失败"))
    for t, why in fails:
        stats["no_data"].append((t, why))
    seen.add(("LX", "净资产覆盖倍数"))

    return stats


def report(store: LeadingIndicatorStore, stats: dict) -> str:
    lines = ["📋 失效指标采集报告", ""]
    lines.append(f"写入历史值: {stats['written']} 条 | 无数据: {len(stats['no_data'])} 条")
    lines.append("")
    if stats["no_data"]:
        lines.append("自动采不到（需人工或网络检索）:")
        for t, why in stats["no_data"]:
            lines.append(f"  {t}: {why}")
        lines.append("")
    # 仍缺数据的指标
    lines.append("仍无最新值的指标:")
    any_missing = False
    for ticker, company, specs in WATCH:
        for s in specs:
            rows = store.get_indicators(ticker)
            row = next((r for r in rows if r.get("indicator_name") == s.name), None)
            if row is None or row.get("latest_value") is None:
                lines.append(f"  {ticker} — {s.name}（{s.invalidation_leg}）")
                any_missing = True
    if not any_missing:
        lines.append("  无 ✅")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--periods", type=int, default=6, help="每个指标回填几期历史")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    store = LeadingIndicatorStore()
    try:
        stats = collect(store, periods=args.periods, dry_run=args.dry_run)
        print(report(store, stats))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
