"""
失效观测 — 每个 open 持仓只追踪能判定失效条件的 1–3 条指标。

与 leading_indicators 全表分开：全表可以很宽，本表必须能回答
「这期失效腿是绿 / 黄 / 红 / 未知」。连续两季才触发的条件，
单期红只表示进入危险区，不是已经失效。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.analysis.leading_indicators import LeadingIndicatorStore

# 持仓规范代码 → 库里可能出现的别名（导入脚本常用短码）
ALIASES = {
    "01810.HK": ["01810.HK", "1810.HK"],
    "02020.HK": ["02020.HK", "2020.HK"],
    "02252.HK": ["02252.HK", "2252.HK"],
    "02498.HK": ["02498.HK", "2498.HK"],
    "03888.HK": ["03888.HK", "3888.HK"],
    "03896.HK": ["03896.HK", "3896.HK"],
    "09626.HK": ["09626.HK", "9626.HK"],
    "09896.HK": ["09896.HK", "9896.HK"],
    "09988.HK": ["09988.HK", "9988.HK"],
    "09999.HK": ["09999.HK", "9999.HK"],
    "LX": ["LX"],
    "SGP.AX": ["SGP.AX", "SGP.ASX"],
}


@dataclass(frozen=True)
class WatchSpec:
    name: str
    description: str
    source: str
    pos: float
    neg: float
    unit: str
    invalidation_leg: str
    consecutive: str  # "1期" / "2季" / "3个月"
    seed: Optional[tuple] = None  # (value, period) optional built-in seed


# ticker, company_name, specs
WATCH = [
    ("01810.HK", "小米集团", [
        WatchSpec("SU7月交付同比", "SU7系列月交付同比", "月度交付", 10, 0, "%",
                  "SU7月交付连续3个月同比下滑", "3个月"),
        WatchSpec("经营现金流", "经营现金流（亿元）", "财报", 0, -1, "亿元",
                  "OCF连续两期转负", "2期",
                  seed=(341.4, "2025")),
        WatchSpec("SU7月交付量", "SU7系列月度交付量（支撑项）", "月度交付", 15000, 8000, "辆/月",
                  "交付绝对量（同比缺失时的辅助）", "1期"),
    ]),
    ("02020.HK", "安踏体育", [
        WatchSpec("FILA增速", "FILA品牌收入或同店同比", "季报", 8, 0, "%",
                  "FILA同店连续两季负增长", "2季"),
        WatchSpec("始祖鸟同店增速", "始祖鸟/亚玛芬同店同比", "季报", 8, 0, "%",
                  "始祖鸟同店连续两季负增长", "2季"),
        WatchSpec("集团毛利率", "集团毛利率", "财报", 60, 55, "%",
                  "集团毛利率跌破55%", "1期",
                  seed=(62.0, "2025")),
    ]),
    ("02252.HK", "微创机器人", [
        WatchSpec("手术量增速", "机器人辅助手术量同比", "季报", 20, 0, "%",
                  "手术量连续两季下滑", "2季"),
        WatchSpec("经营现金流", "经营现金流（亿元）", "财报", 0, -1, "亿元",
                  "经营现金流持续大幅为负", "2期",
                  seed=(-0.2, "2025")),
        WatchSpec("现金跑道月数", "现金及等价物 / 月均经营现金流出", "财报", 18, 12, "月",
                  "现金不够覆盖18个月运营", "1期"),
    ]),
    ("02498.HK", "速腾聚创", [
        WatchSpec("车型定点数", "已定点量产车型数量", "公告", 50, 20, "个",
                  "定点数连续两季净减少或份额被挤压", "2季"),
        WatchSpec("毛利率", "集团毛利率", "财报", 25, 20, "%",
                  "毛利率跌破20%且无盈利路径", "1期",
                  seed=(26.5, "2025")),
        WatchSpec("经营现金流", "经营现金流（亿元）", "财报", 0, -1, "亿元",
                  "盈利路径（OCF仍负则路径未通）", "1期",
                  seed=(-5.8, "2025")),
    ]),
    ("03888.HK", "金山软件", [
        WatchSpec("办公软件收入同比", "WPS/办公软件及服务收入同比（无分部时暂用集团营收同比）", "季报", 5, 0, "%",
                  "WPS/办公收入连续两季下滑", "2季",
                  seed=(-6.2, "2025")),
        WatchSpec("办公毛利率", "办公软件毛利率（无分部时暂用集团毛利率）", "财报", 75, 70, "%",
                  "办公毛利率因AI免费化显著受冲击", "1期",
                  seed=(81.2, "2025")),
    ]),
    ("03896.HK", "金山云", [
        WatchSpec("AI云收入增速", "AI云业务收入同比", "季报", 30, 20, "%",
                  "AI云增速连续两季低于20%", "2季"),
        WatchSpec("经营现金流营收比", "经营现金流/营收", "季报", 50, 20, "%",
                  "OCF/营收持续恶化", "2季"),
        WatchSpec("大客户CapEx", "主要云客户资本开支同比", "季报/行业", 10, -5, "%",
                  "大客户CapEx下调（与OCF恶化同时才触发）", "1期"),
    ]),
    ("09626.HK", "哔哩哔哩", [
        WatchSpec("经营利润", "经营利润（亿元）", "财报", 1, 0, "亿元",
                  "经营利润再次转负", "1期",
                  seed=(11.2, "2025")),
        WatchSpec("DAU增速", "日活同比", "季报", 10, 0, "%",
                  "DAU连续两季下滑", "2季"),
        WatchSpec("广告收入增速", "广告收入同比", "季报", 10, 0, "%",
                  "广告收入连续两季下滑", "2季"),
    ]),
    ("09896.HK", "名创优品", [
        WatchSpec("海外同店增速", "海外同店销售同比", "季报", 5, 0, "%",
                  "海外同店连续两季负增长", "2季"),
        WatchSpec("存货周转天数", "存货周转天数（越低越好）", "财报", 50, 80, "天",
                  "存货周转明显变慢", "2季"),
        WatchSpec("IP授权收入占比", "IP授权产品收入占比", "季报", 25, 15, "%",
                  "IP授权停滞", "2季"),
    ]),
    ("09988.HK", "阿里巴巴", [
        WatchSpec("云收入增速", "阿里云收入同比", "季报", 10, 0, "%",
                  "云收入连续两季减速", "2季"),
        WatchSpec("云经分利润率", "云业务经分利润率", "季报", 8, 3, "%",
                  "云经分利润率下滑（需与增速同时）", "2季"),
        WatchSpec("中国零售增速", "中国电商零售收入同比（份额代理）", "季报", 5, 0, "%",
                  "核心电商份额持续丢失", "2季"),
    ]),
    ("09999.HK", "网易", [
        WatchSpec("新游流水", "新上线游戏月流水", "行业数据", 5, 1, "亿元/月",
                  "无新爆款接力", "2季"),
        WatchSpec("游戏毛利率", "游戏或集团毛利率", "财报", 58, 50, "%",
                  "版号/监管显著压缩游戏毛利率", "1期",
                  seed=(64.3, "2025")),
        WatchSpec("游戏版号获取", "季度获得版号数量", "公告", 3, 0, "个/季",
                  "主力流水下滑且无新游（版号是辅助）", "1期"),
    ]),
    ("LX", "乐信", [
        WatchSpec("净资产覆盖倍数", "每股净资产 / 股价（>1 表示资产覆盖市值）", "财报+行情", 1.2, 1.0, "倍",
                  "每股净资产不再覆盖市值", "1期"),
        WatchSpec("不良率", "不良贷款率 / 逾期率", "季报", 3, 5, "%",
                  "不良率/信贷成本连续两季上升", "2季"),
        WatchSpec("每股股息", "最近一期每股股息（USD）", "公告", 0.05, 0, "USD",
                  "取消或大幅削减股息", "1期"),
    ]),
    ("SGP.AX", "Stockland", [
        WatchSpec("住宅合同同比", "住宅预售/合同量同比", "季报", 5, 0, "%",
                  "住宅合同量连续两季下滑", "2季"),
        WatchSpec("NOI增速", "净营运收入同比", "财报", 3, 0, "%",
                  "NOI转负增长", "1期"),
        WatchSpec("净负债率", "净负债 / 总资产（越低越好）", "财报", 25, 40, "%",
                  "净负债率上升（需与NOI同时）", "1期"),
    ]),
]


def all_tickers() -> list[str]:
    return [t for t, _, _ in WATCH]


def specs_for(ticker: str) -> list[WatchSpec]:
    for t, _, specs in WATCH:
        if t == ticker:
            return list(specs)
    return []


def sync(store: LeadingIndicatorStore) -> dict:
    """Register watch indicators on canonical tickers and seed known values."""
    added = 0
    seeded = 0
    copied = 0
    for ticker, name, specs in WATCH:
        for spec in specs:
            store.add_indicator(
                ticker=ticker,
                company_name=name,
                indicator_name=spec.name,
                description=spec.description,
                source=spec.source,
                threshold_positive=spec.pos,
                threshold_negative=spec.neg,
                unit=spec.unit,
                category="失效观测",
                notes=f"失效腿:{spec.invalidation_leg}；判定:{spec.consecutive}",
                dimension_map={"negative": {"growth": -1}},
            )
            added += 1
            row = _get(store, ticker, spec.name)
            if row and row.get("latest_value") is None:
                copied_row = _find_alias_value(store, ticker, spec.name)
                if copied_row and copied_row.get("latest_value") is not None:
                    store.update_value(
                        ticker, spec.name,
                        float(copied_row["latest_value"]),
                        copied_row.get("latest_period") or "",
                    )
                    copied += 1
                    row = _get(store, ticker, spec.name)
            if (row is None or row.get("latest_value") is None) and spec.seed:
                val, period = spec.seed
                store.update_value(ticker, spec.name, float(val), period)
                seeded += 1
    return {"registered": added, "seeded": seeded, "copied": copied}


def _get(store: LeadingIndicatorStore, ticker: str, name: str) -> Optional[dict]:
    for r in store.get_indicators(ticker):
        if r.get("indicator_name") == name:
            return r
    return None


def _find_alias_value(store: LeadingIndicatorStore, ticker: str, name: str) -> Optional[dict]:
    for alt in ALIASES.get(ticker, [ticker]):
        if alt == ticker:
            continue
        row = _get(store, alt, name)
        if row and row.get("latest_value") is not None:
            return row
    return None


def snapshot_for_ticker(store: LeadingIndicatorStore, ticker: str) -> list[dict]:
    specs = specs_for(ticker)
    out = []
    for spec in specs:
        row = _get(store, ticker, spec.name)
        value = row.get("latest_value") if row else None
        status = row.get("status") if row else "unknown"
        if value is None:
            status = "unknown"
        out.append({
            "name": spec.name,
            "status": status,
            "value": value,
            "unit": spec.unit,
            "period": (row or {}).get("latest_period") or "",
            "leg": spec.invalidation_leg,
            "consecutive": spec.consecutive,
            "pos": spec.pos,
            "neg": spec.neg,
        })
    return out


def format_watch(store: LeadingIndicatorStore, positions) -> str:
    """positions: iterable of Position with .ticker .company_name .invalidation"""
    icon = {"positive": "🟢", "negative": "🔴", "neutral": "🟡", "unknown": "❓"}
    lines = ["  失效观测（只看持仓，单期红≠已经失效）", ""]
    unknown = 0
    red = 0
    for p in positions:
        rows = snapshot_for_ticker(store, p.ticker)
        name = p.company_name or p.ticker
        lines.append(f"  {p.ticker}  {name}")
        lines.append(f"    失效: {p.invalidation}")
        if not rows:
            lines.append("    ❓ 未配置观测（不在 WATCH 表）")
            unknown += 1
            continue
        for r in rows:
            ic = icon.get(r["status"], "❓")
            if r["status"] == "unknown":
                unknown += 1
                val = "—"
            else:
                if r["status"] == "negative":
                    red += 1
                val = f"{r['value']}{r['unit']}"
                if r["period"]:
                    val += f" [{r['period']}]"
            tag = r["consecutive"]
            lines.append(f"    {ic} {r['name']}: {val}  ({tag})")
        lines.append("")
    lines.append(f"  汇总: 红 {red}  未知 {unknown}  （未知先手填，不要用空值判失效）")
    return "\n".join(lines)
