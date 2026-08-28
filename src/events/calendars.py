"""
宏观事件日历 — 固定日期的重要经济/政策事件
覆盖: 美联储、中国数据、澳洲RBA、港股通休市

所有用户可见文本为中文。
"""

from datetime import date, datetime
from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# 2026年下半年宏观事件（可手动更新）
# ---------------------------------------------------------------------------

MACRO_EVENTS_2026: List[Dict] = [
    # ===== 7月 =====
    {"date": "2026-07-15", "title": "中国Q2 GDP", "type": "macro", "impact": "high",
     "description": "二季度GDP增速，反映经济复苏力度"},
    {"date": "2026-07-30", "title": "美联储FOMC利率决议", "type": "macro", "impact": "high",
     "description": "关注降息信号和点阵图变化"},

    # ===== 8月 =====
    {"date": "2026-08-12", "title": "美国7月CPI", "type": "macro", "impact": "high",
     "description": "通胀数据，影响美联储降息节奏"},
    {"date": "2026-08-15", "title": "中国7月社零/工业/固投", "type": "macro", "impact": "medium",
     "description": "月度经济数据，反映消费和工业复苏"},
    {"date": "2026-08-20", "title": "中国LPR报价", "type": "macro", "impact": "medium",
     "description": "贷款市场报价利率，关注是否降息"},

    # ===== 9月 =====
    {"date": "2026-09-10", "title": "美国8月CPI", "type": "macro", "impact": "high",
     "description": "通胀趋势确认"},
    {"date": "2026-09-17", "title": "美联储FOMC利率决议+点阵图", "type": "macro", "impact": "high",
     "description": "三季度最重要会议，含经济预测和点阵图更新"},
    {"date": "2026-09-20", "title": "中国LPR报价", "type": "macro", "impact": "medium",
     "description": "贷款市场报价利率"},

    # ===== 10月 =====
    {"date": "2026-10-01", "title": "中国国庆节 港股通关闭", "type": "macro", "impact": "low",
     "description": "港股通10月1-7日关闭，南向资金暂停"},
    {"date": "2026-10-15", "title": "中国Q3 GDP", "type": "macro", "impact": "high",
     "description": "三季度GDP增速"},
    {"date": "2026-10-29", "title": "美联储FOMC利率决议", "type": "macro", "impact": "high",
     "description": "利率决议"},

    # ===== 11月 =====
    {"date": "2026-11-05", "title": "美国中期选举", "type": "macro", "impact": "high",
     "description": "国会选举，影响政策走向和市场情绪"},
    {"date": "2026-11-12", "title": "美国10月CPI", "type": "macro", "impact": "high",
     "description": "通胀数据"},

    # ===== 12月 =====
    {"date": "2026-12-10", "title": "美国11月CPI", "type": "macro", "impact": "high",
     "description": "通胀数据"},
    {"date": "2026-12-17", "title": "美联储FOMC利率决议+点阵图", "type": "macro", "impact": "high",
     "description": "年度最后一次会议，含全年经济预测更新"},

    # ===== 澳洲RBA =====
    {"date": "2026-07-08", "title": "澳洲RBA利率决议", "type": "macro", "impact": "medium",
     "description": "澳大利亚储备银行利率决议，影响SGP.ASX"},
    {"date": "2026-08-05", "title": "澳洲RBA利率决议", "type": "macro", "impact": "medium",
     "description": "澳大利亚储备银行利率决议"},
    {"date": "2026-09-02", "title": "澳洲RBA利率决议", "type": "macro", "impact": "medium",
     "description": "澳大利亚储备银行利率决议"},
    {"date": "2026-10-07", "title": "澳洲RBA利率决议", "type": "macro", "impact": "medium",
     "description": "澳大利亚储备银行利率决议"},
    {"date": "2026-11-04", "title": "澳洲RBA利率决议", "type": "macro", "impact": "medium",
     "description": "澳大利亚储备银行利率决议"},
    {"date": "2026-12-02", "title": "澳洲RBA利率决议", "type": "macro", "impact": "medium",
     "description": "澳大利亚储备银行利率决议"},
]


# ---------------------------------------------------------------------------
# 公司财报日历（季度，按惯例推测，需根据实际公告更新）
# ---------------------------------------------------------------------------

EARNINGS_CALENDAR_2026: List[Dict] = [
    # Q2 2026 财报（通常8-9月发布）
    {"date": "2026-08-20", "ticker": "1810.HK", "title": "小米Q2 2026财报", "type": "earnings",
     "impact": "high", "description": "关注SU7交付量、AI大模型进展、海外EV"},
    {"date": "2026-08-15", "ticker": "09988.HK", "title": "阿里巴巴Q2 2026财报", "type": "earnings",
     "impact": "high", "description": "关注阿里云增速、国际电商、AI投入"},
    {"date": "2026-08-25", "ticker": "9999.HK", "title": "网易Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注新游pipeline"},
    {"date": "2026-08-28", "ticker": "3888.HK", "title": "金山软件Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注WPS AI商业化"},
    {"date": "2026-08-28", "ticker": "3896.HK", "title": "金山云Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注AI算力需求、亏损收窄"},
    {"date": "2026-09-05", "ticker": "LX", "title": "乐信Q2 2026财报", "type": "earnings",
     "impact": "high", "description": "关注核心净利润、资产质量、分红"},
    {"date": "2026-08-25", "ticker": "2252.HK", "title": "微创机器人Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注手术机器人装机量、海外进展"},
    {"date": "2026-08-20", "ticker": "2498.HK", "title": "速腾聚创Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注LiDAR装车量、新客户"},
    {"date": "2026-08-22", "ticker": "9626.HK", "title": "B站Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注广告收入、盈利路径"},
    {"date": "2026-08-18", "ticker": "9896.HK", "title": "名创优品Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注海外门店扩张"},
    {"date": "2026-09-05", "ticker": "1361.HK", "title": "361度Q2 2026财报", "type": "earnings",
     "impact": "low", "description": "关注营收增速"},
    {"date": "2026-08-25", "ticker": "2020.HK", "title": "安踏Q2 2026财报", "type": "earnings",
     "impact": "medium", "description": "关注FILA增速、始祖鸟"},
    {"date": "2026-09-05", "ticker": "SGP.ASX", "title": "Stockland年报", "type": "earnings",
     "impact": "medium", "description": "关注澳洲地产销售、利率影响"},
]


def get_all_macro_events(year: int = 2026, month: int = None) -> List[Dict]:
    """获取所有宏观事件，可按月份过滤。"""
    events = [e for e in MACRO_EVENTS_2026 if e["date"].startswith(str(year))]
    if month:
        prefix = f"{year}-{month:02d}"
        events = [e for e in events if e["date"].startswith(prefix)]
    return sorted(events, key=lambda e: e["date"])


def get_all_earnings(year: int = 2026, month: int = None) -> List[Dict]:
    """获取所有财报事件，可按月份过滤。"""
    events = [e for e in EARNINGS_CALENDAR_2026 if e["date"].startswith(str(year))]
    if month:
        prefix = f"{year}-{month:02d}"
        events = [e for e in events if e["date"].startswith(prefix)]
    return sorted(events, key=lambda e: e["date"])


def get_upcoming_events(days: int = 30) -> List[Dict]:
    """获取未来N天的所有事件（宏观+财报）。"""
    today = date.today()
    cutoff = today.isoformat()
    end = date.fromordinal(today.toordinal() + days).isoformat()

    all_events = MACRO_EVENTS_2026 + EARNINGS_CALENDAR_2026
    upcoming = [e for e in all_events if cutoff <= e["date"] <= end]
    return sorted(upcoming, key=lambda e: e["date"])


def get_events_for_date(target_date: str) -> List[Dict]:
    """获取指定日期的所有事件。"""
    all_events = MACRO_EVENTS_2026 + EARNINGS_CALENDAR_2026
    return [e for e in all_events if e["date"] == target_date]
