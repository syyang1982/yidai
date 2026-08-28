"""
事件采集器 — 从多个来源收集预知事件
来源: 内置日历 + Google News RSS + 东方财富API

所有用户可见文本为中文。
"""

import json
import os
import re
import subprocess
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional

from src.events.models import MarketEvent
from src.events.calendars import (
    get_upcoming_events,
    get_all_macro_events,
    get_all_earnings,
)


class EventCollector:
    """事件采集器 — 从多个来源收集预知事件。"""

    def __init__(self, project_root: str = None):
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
        self.project_root = project_root

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def collect_all(self, tickers: List[str] = None) -> List[MarketEvent]:
        """运行所有采集器，去重后返回。"""
        events: List[MarketEvent] = []

        # 1) 内置宏观日历
        events.extend(self.collect_macro_events())

        # 2) 内置财报日历
        events.extend(self.collect_earnings_dates(tickers or []))

        # 3) RSS搜索产品发布/行业新闻（仅对指定ticker）
        if tickers:
            events.extend(self.collect_product_launches(tickers))

        # 去重（按type+title+date，避免宏观事件和财报事件互相覆盖）
        seen = set()
        unique = []
        for e in events:
            key = (e.event_type, e.title, e.event_date)
            if key not in seen:
                seen.add(key)
                unique.append(e)

        return unique

    # ------------------------------------------------------------------
    # 宏观事件
    # ------------------------------------------------------------------
    def collect_macro_events(self, days: int = 90) -> List[MarketEvent]:
        """从内置日历采集宏观事件。"""
        raw = get_all_macro_events()  # 只获取宏观事件，不含财报
        events = []
        for item in raw:
            events.append(MarketEvent(
                event_type=item.get("type", "macro"),
                title=item["title"],
                description=item.get("description", ""),
                event_date=item["date"],
                affected_tickers=self._infer_macro_tickers(item["title"]),
                impact_level=item.get("impact", "medium"),
                source="内置日历",
            ))
        return events

    # ------------------------------------------------------------------
    # 财报日期
    # ------------------------------------------------------------------
    def collect_earnings_dates(self, tickers: List[str]) -> List[MarketEvent]:
        """从内置日历采集财报事件。"""
        raw = get_all_earnings()
        events = []
        for item in raw:
            # 如果指定了tickers，只保留相关的
            if tickers and item.get("ticker") not in tickers:
                continue
            events.append(MarketEvent(
                event_type="earnings",
                title=item["title"],
                description=item.get("description", ""),
                event_date=item["date"],
                affected_tickers=[item.get("ticker", "")],
                impact_level=item.get("impact", "medium"),
                source="财报日历",
            ))
        return events

    # ------------------------------------------------------------------
    # 产品发布/行业新闻（RSS搜索）
    # ------------------------------------------------------------------
    def collect_product_launches(self, tickers: List[str]) -> List[MarketEvent]:
        """通过RSS搜索产品发布和技术里程碑事件。"""
        # 公司名映射
        ticker_names = {
            "1810.HK": "小米", "09988.HK": "阿里巴巴", "3896.HK": "金山云",
            "3888.HK": "金山软件", "2252.HK": "微创机器人", "2498.HK": "速腾聚创",
            "9626.HK": "B站", "9999.HK": "网易", "9896.HK": "名创优品",
            "1361.HK": "361度", "2020.HK": "安踏", "LX": "乐信",
            "159227.SZ": "航空航天", "SGP.ASX": "Stockland",
        }

        events = []
        for ticker in tickers:
            name = ticker_names.get(ticker, ticker)
            # 搜索关键词: 公司名 + 产品/发布/合作
            query = f"{name} 产品 发布 合作 2026"
            articles = self._search_rss(query, hours=168)  # 7天窗口
            for art in articles:
                events.append(MarketEvent(
                    event_type="product",
                    title=art["title"],
                    description=art.get("description", ""),
                    event_date=art.get("date", date.today().isoformat()),
                    affected_tickers=[ticker],
                    impact_level="medium",
                    source="Google News RSS",
                    source_url=art.get("link", ""),
                ))

        return events

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _infer_macro_tickers(self, title: str) -> List[str]:
        """根据宏观事件标题推断受影响的股票。"""
        tickers = []
        lower = title.lower()

        # 美联储/通胀 → 全组合受影响（标记为宏观）
        if any(k in title for k in ["美联储", "CPI", "通胀"]):
            tickers.append("宏观")

        # 澳洲RBA → SGP.ASX
        if "RBA" in title or "澳洲" in title:
            tickers.append("SGP.ASX")

        # 中国GDP/PMI/LPR → 中国相关持仓
        if any(k in title for k in ["中国", "LPR", "社零"]):
            tickers.extend(["1810.HK", "09988.HK", "3896.HK"])

        # 港股通 → 所有港股
        if "港股通" in title:
            tickers.append("港股通")

        return tickers if tickers else ["宏观"]

    def _search_rss(self, query: str, hours: int = 24) -> List[Dict]:
        """Google News RSS搜索，返回标题+描述+链接+时间。"""
        encoded = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"

        try:
            r = subprocess.run(
                ["curl", "-s", "-m", "10", url],
                capture_output=True, timeout=15
            )
            xml = r.stdout.decode("utf-8", errors="replace")
        except Exception:
            return []

        titles = re.findall(r'<title>(.*?)</title>', xml)
        links = re.findall(r'<link>(.*?)</link>', xml)
        descs = re.findall(
            r'<description><!\[CDATA\[(.*?)\]\]></description>', xml, re.DOTALL
        )
        pub_dates = re.findall(r'<pubDate>(.*?)</pubDate>', xml)

        # 跳过第一个title（feed title）
        if len(titles) > 1:
            titles = titles[1:]

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        articles = []
        for i in range(min(len(titles), len(links))):
            title = re.sub(r'<[^>]+>', '', titles[i]).strip()
            link = links[i].strip() if i < len(links) else ""
            desc = re.sub(r'<[^>]+>', '', descs[i]).strip() if i < len(descs) else ""

            # 解析时间
            art_date = date.today().isoformat()
            if i < len(pub_dates):
                try:
                    # RFC 2822 format: Wed, 10 Jul 2026 08:00:00 GMT
                    dt = datetime.strptime(pub_dates[i].strip()[:25], "%a, %d %b %Y %H:%M:%S")
                    if dt < cutoff:
                        continue
                    art_date = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

            articles.append({
                "title": title,
                "link": link,
                "description": desc[:200],
                "date": art_date,
            })

        return articles
