"""Tests for ThemeMapper."""

import json
import pytest
from pathlib import Path

from src.events.theme_mapper import ThemeMapper


@pytest.fixture
def mapper(tmp_path):
    """Create a ThemeMapper backed by a temporary mapping file."""
    mapping = {
        "themes": [
            {
                "theme": "航空航天/中国星链",
                "keywords": ["长征火箭", "可回收火箭", "商业航天", "卫星发射", "星网", "中国星链", "千帆星座", "G60"],
                "affected_tickers": [
                    {"ticker": "159227.SZ", "relation": "直接", "note": "航空航天ETF"},
                    {"ticker": "铖昌科技", "relation": "直接", "note": "星载T/R芯片"}
                ],
                "priority": "high"
            },
            {
                "theme": "石油/黄金/大宗商品",
                "keywords": ["油价", "原油", "OPEC", "黄金", "金价", "美联储", "降息", "避险", "地缘冲突"],
                "affected_tickers": [{"ticker": "GLD", "relation": "直接", "note": "黄金ETF"}],
                "priority": "high"
            },
            {
                "theme": "铝/稀土/稀有金属",
                "keywords": ["铝", "氧化铝", "稀土", "钕铁硼", "锗", "镓", "锑", "关键矿产", "出口管制"],
                "affected_tickers": [
                    {"ticker": "中国铝业", "relation": "直接", "note": "铝龙头"},
                    {"ticker": "北方稀土", "relation": "直接", "note": "稀土龙头"}
                ],
                "priority": "high"
            },
            {
                "theme": "AI大模型/算力/云",
                "keywords": ["GPT", "大模型", "AI芯片", "算力", "GPU", "英伟达", "通义千问", "DeepSeek", "云计算", "数据中心"],
                "affected_tickers": [
                    {"ticker": "3896.HK", "relation": "直接", "note": "金山云"},
                    {"ticker": "09988.HK", "relation": "直接", "note": "阿里云"},
                    {"ticker": "1810.HK", "relation": "间接", "note": "小米AI"}
                ],
                "priority": "high"
            },
            {
                "theme": "小米生态",
                "keywords": ["小米", "SU7", "雷军", "小米汽车", "小米手机", "IoT"],
                "affected_tickers": [{"ticker": "1810.HK", "relation": "直接"}],
                "priority": "high"
            },
            {
                "theme": "阿里巴巴生态",
                "keywords": ["阿里巴巴", "阿里云", "通义", "淘宝", "天猫", "菜鸟", "蚂蚁"],
                "affected_tickers": [{"ticker": "09988.HK", "relation": "直接"}],
                "priority": "high"
            },
            {
                "theme": "手术机器人/医疗机器人",
                "keywords": ["手术机器人", "达芬奇", "微创", "医疗机器人", "腔镜", "图迈"],
                "affected_tickers": [{"ticker": "2252.HK", "relation": "直接"}],
                "priority": "high"
            },
            {
                "theme": "永辉超市/新零售",
                "keywords": ["永辉超市", "新零售", "胖东来", "生鲜"],
                "affected_tickers": [{"ticker": "永辉超市", "relation": "直接"}],
                "priority": "medium"
            },
            {
                "theme": "澳洲房地产/利率",
                "keywords": ["澳洲利率", "RBA", "澳洲房价", "澳洲联储", "澳洲通胀"],
                "affected_tickers": [{"ticker": "SGP.ASX", "relation": "直接"}],
                "priority": "medium"
            },
            {
                "theme": "LiDAR/自动驾驶感知",
                "keywords": ["激光雷达", "LiDAR", "自动驾驶", "车路协同"],
                "affected_tickers": [{"ticker": "2498.HK", "relation": "直接"}],
                "priority": "medium"
            },
            {
                "theme": "内存/存储芯片",
                "keywords": ["内存", "DRAM", "NAND", "HBM", "存储芯片", "美光", "长鑫存储"],
                "affected_tickers": [{"ticker": "MU", "relation": "直接"}],
                "priority": "medium"
            },
            {
                "theme": "高通/移动芯片",
                "keywords": ["高通", "Qualcomm", "骁龙", "手机芯片", "5G基带"],
                "affected_tickers": [
                    {"ticker": "QCOM", "relation": "直接"},
                    {"ticker": "1810.HK", "relation": "间接"}
                ],
                "priority": "medium"
            },
            {
                "theme": "新能源汽车/自动驾驶",
                "keywords": ["新能源车", "电动车", "充电桩", "固态电池"],
                "affected_tickers": [{"ticker": "1810.HK", "relation": "直接"}],
                "priority": "medium"
            },
            {
                "theme": "消费/国潮",
                "keywords": ["消费", "国潮", "体育", "运动鞋服", "出海"],
                "affected_tickers": [{"ticker": "1361.HK", "relation": "直接"}],
                "priority": "low"
            },
            {
                "theme": "游戏/内容",
                "keywords": ["版号", "游戏", "B站", "网易"],
                "affected_tickers": [{"ticker": "9626.HK", "relation": "直接"}],
                "priority": "low"
            },
            {
                "theme": "助贷/消费金融",
                "keywords": ["助贷", "消费金融", "利率上限", "网络小贷"],
                "affected_tickers": [{"ticker": "LX", "relation": "直接"}],
                "priority": "low"
            }
        ]
    }
    path = tmp_path / "theme_mapping.json"
    path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return ThemeMapper(mapping_path=path)


# ── match_news_to_portfolio ──────────────────────────────────────────

class TestMatchNewsToPortfolio:

    def test_aerospace_match(self, mapper):
        results = mapper.match_news_to_portfolio("长征火箭可回收发射成功")
        tickers = {r["ticker"] for r in results}
        assert "159227.SZ" in tickers
        assert any(r["theme"] == "航空航天/中国星链" for r in results)

    def test_australia_rba_match(self, mapper):
        results = mapper.match_news_to_portfolio("RBA降息25基点")
        tickers = {r["ticker"] for r in results}
        assert "SGP.ASX" in tickers
        assert any(r["theme"] == "澳洲房地产/利率" for r in results)

    def test_xiaomi_match(self, mapper):
        results = mapper.match_news_to_portfolio("小米SU7交付量破万")
        tickers = {r["ticker"] for r in results}
        assert "1810.HK" in tickers
        assert any(r["theme"] == "小米生态" for r in results)

    def test_dram_match(self, mapper):
        results = mapper.match_news_to_portfolio("DRAM价格暴涨")
        tickers = {r["ticker"] for r in results}
        assert "MU" in tickers
        assert any(r["theme"] == "内存/存储芯片" for r in results)

    def test_unrelated_text_returns_empty(self, mapper):
        results = mapper.match_news_to_portfolio("今天天气不错适合散步")
        assert results == []

    def test_multiple_themes_match(self, mapper):
        results = mapper.match_news_to_portfolio("小米SU7电动车交付创新高雷军庆祝")
        themes = {r["theme"] for r in results}
        assert "小米生态" in themes
        # "电动车" also matches 新能源汽车/自动驾驶
        assert "新能源汽车/自动驾驶" in themes

    def test_confidence_calculation(self, mapper):
        results = mapper.match_news_to_portfolio("小米SU7")
        xiaomi = [r for r in results if r["theme"] == "小米生态"]
        assert len(xiaomi) == 1
        # 2 keywords matched out of 6 total = 0.333
        assert xiaomi[0]["confidence"] == pytest.approx(2 / 6, abs=0.01)

    def test_keywords_matched_present(self, mapper):
        results = mapper.match_news_to_portfolio("DRAM价格暴涨")
        mu = [r for r in results if r["ticker"] == "MU"]
        assert mu[0]["keywords_matched"] == ["DRAM"]


# ── get_theme_keywords ──────────────────────────────────────────────

class TestGetThemeKeywords:

    def test_known_ticker(self, mapper):
        kws = mapper.get_theme_keywords("1810.HK")
        # 1810.HK appears in 小米生态, AI大模型, 高通/移动芯片, 新能源汽车
        assert "小米" in kws
        assert "GPT" in kws or "大模型" in kws
        assert "新能源车" in kws or "电动车" in kws

    def test_unknown_ticker_returns_empty(self, mapper):
        kws = mapper.get_theme_keywords("FAKE.TICKER")
        assert kws == []

    def test_no_duplicates(self, mapper):
        kws = mapper.get_theme_keywords("1810.HK")
        assert len(kws) == len(set(kws))


# ── find_related_themes ─────────────────────────────────────────────

class TestFindRelatedThemes:

    def test_single_keyword(self, mapper):
        results = mapper.find_related_themes(["DRAM"])
        assert len(results) >= 1
        assert results[0]["theme"] == "内存/存储芯片"

    def test_multiple_keywords_across_themes(self, mapper):
        results = mapper.find_related_themes(["小米", "DRAM", "RBA"])
        themes = {r["theme"] for r in results}
        assert "小米生态" in themes
        assert "内存/存储芯片" in themes
        assert "澳洲房地产/利率" in themes

    def test_no_match(self, mapper):
        results = mapper.find_related_themes(["完全无关的词"])
        assert results == []


# ── get_all_tickers ─────────────────────────────────────────────────

class TestGetAllTickers:

    def test_returns_deduplicated_list(self, mapper):
        tickers = mapper.get_all_tickers()
        assert len(tickers) == len(set(tickers))

    def test_contains_expected_tickers(self, mapper):
        tickers = mapper.get_all_tickers()
        assert "1810.HK" in tickers
        assert "09988.HK" in tickers
        assert "LX" in tickers
        assert "MU" in tickers

    def test_count(self, mapper):
        tickers = mapper.get_all_tickers()
        # Count unique tickers in the mapping: let's just verify it's > 10
        assert len(tickers) > 10
