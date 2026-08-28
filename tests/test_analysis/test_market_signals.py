"""Tests for market signal alerts (W1.2)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.market_signals import (
    score_announcement_sentiment,
    score_industry_health,
    detect_management_change,
)


# =========================================================================
# 1. Announcement Sentiment
# =========================================================================


class TestSentimentPositive:
    """Mostly positive keywords → positive sentiment, score ≥ 4."""

    def test_all_positive(self):
        text = "公司业绩增长显著，实现重大突破，创新技术超预期"
        result = score_announcement_sentiment(text)
        assert result["sentiment"] == "positive"
        assert result["positive_count"] > 0
        assert result["negative_count"] == 0
        assert result["score"] >= 4

    def test_positive_keywords_detected(self):
        text = "公司与合作伙伴签约新订单，实现盈利增长"
        result = score_announcement_sentiment(text)
        assert "合作" in result["keywords_found"]
        assert "增长" in result["keywords_found"]
        assert "盈利" in result["keywords_found"]


class TestSentimentNegative:
    """Mostly negative keywords → negative sentiment, score ≤ 2."""

    def test_all_negative(self):
        text = "公司面临重大诉讼，业绩亏损，存在违约风险，被处以罚款"
        result = score_announcement_sentiment(text)
        assert result["sentiment"] == "negative"
        assert result["negative_count"] > 0
        assert result["positive_count"] == 0
        assert result["score"] <= 2

    def test_negative_keywords_detected(self):
        text = "公司因违规被立案调查，面临退市风险"
        result = score_announcement_sentiment(text)
        assert "违规" in result["keywords_found"]
        assert "退市" in result["keywords_found"]
        assert "风险" in result["keywords_found"]


class TestSentimentNeutral:
    """No keywords or balanced mix → neutral, score ≈ 3."""

    def test_no_keywords(self):
        text = "公司召开年度股东大会，审议相关议案"
        result = score_announcement_sentiment(text)
        assert result["sentiment"] == "neutral"
        assert result["negative_count"] == 0
        assert result["positive_count"] == 0
        assert result["score"] == 3

    def test_mixed_balanced(self):
        text = "公司业绩增长，但面临诉讼风险"
        result = score_announcement_sentiment(text)
        # 1 positive (增长) vs 1 negative (风险, 诉讼) → score ≈ 3
        assert result["score"] in (2, 3)


class TestSentimentEdgeCases:
    """Edge cases: empty text, whitespace."""

    def test_empty_string(self):
        result = score_announcement_sentiment("")
        assert result["sentiment"] == "neutral"
        assert result["score"] == 3
        assert result["keywords_found"] == []

    def test_whitespace_only(self):
        result = score_announcement_sentiment("   \n\t  ")
        assert result["sentiment"] == "neutral"
        assert result["score"] == 3

    def test_keyword_deduplication(self):
        text = "增长增长增长，突破突破"
        result = score_announcement_sentiment(text)
        assert result["keywords_found"] == ["增长", "突破"]


# =========================================================================
# 2. Industry Health
# =========================================================================


class TestIndustryHealthExpanding:
    """All metrics above expanding thresholds → score ≥ 4."""

    def test_expanding_semiconductor(self):
        metrics = {
            "pmi": 52.0,
            "sales_growth": 20.0,
            "inventory_ratio": 1.0,
            "capacity_utilization": 88.0,
        }
        result = score_industry_health("半导体", metrics)
        assert result["score"] >= 4
        assert result["status"] == "expanding"

    def test_expanding_default_industry(self):
        metrics = {
            "pmi": 52.0,
            "sales_growth": 15.0,
            "inventory_ratio": 1.0,
            "capacity_utilization": 85.0,
        }
        result = score_industry_health("未知行业", metrics)
        assert result["score"] >= 4
        assert result["status"] == "expanding"


class TestIndustryHealthContracting:
    """All metrics below contracting thresholds → score ≤ 1."""

    def test_contracting(self):
        metrics = {
            "pmi": 47.0,
            "sales_growth": -5.0,
            "inventory_ratio": 2.0,
            "capacity_utilization": 60.0,
        }
        result = score_industry_health("消费", metrics)
        assert result["score"] <= 1
        assert result["status"] == "contracting"


class TestIndustryHealthStable:
    """Metrics in between → stable, score 2-3."""

    def test_stable_mixed(self):
        metrics = {
            "pmi": 50.0,  # neutral
            "sales_growth": 5.0,  # neutral for default
        }
        result = score_industry_health("default", metrics)
        assert result["status"] == "stable"
        assert 2 <= result["score"] <= 3


class TestIndustryHealthNoData:
    """Empty / no metrics → default neutral score."""

    def test_empty_dict(self):
        result = score_industry_health("半导体", {})
        assert result["score"] == 3
        assert result["status"] == "stable"
        assert "无数据" in result["details"][0]

    def test_none_values(self):
        result = score_industry_health("新能源", {"pmi": None, "sales_growth": None})
        assert result["score"] == 3

    def test_partial_data(self):
        metrics = {"pmi": 52.0}
        result = score_industry_health("半导体", metrics)
        assert result["score"] >= 3
        # other metrics should be listed as missing
        assert any("缺失" in d for d in result["details"])


class TestIndustryHealthInventoryInversion:
    """Inventory ratio: lower is better (inverted logic)."""

    def test_low_inventory_is_positive(self):
        metrics = {"inventory_ratio": 0.8}
        result = score_industry_health("default", metrics)
        # 0.8 ≤ 1.2 → expanding on this metric
        assert result["score"] >= 3

    def test_high_inventory_is_negative(self):
        metrics = {"inventory_ratio": 2.5}
        result = score_industry_health("default", metrics)
        # 2.5 ≥ 1.8 → contracting on this metric
        assert result["score"] <= 2


# =========================================================================
# 3. Management Change Detection
# =========================================================================


class TestManagementChangeDetection:
    """Basic management change keyword detection."""

    def test_detect_resignation(self):
        announcements = ["公司董事长因个人原因辞职"]
        results = detect_management_change(announcements)
        assert len(results) == 1
        assert results[0]["keyword"] == "辞职"
        assert results[0]["severity"] == "high"

    def test_detect_new_appointment(self):
        announcements = ["公司聘任张三为新任总经理"]
        results = detect_management_change(announcements)
        assert len(results) >= 1
        keywords = [r["keyword"] for r in results]
        assert "聘任" in keywords or "新任" in keywords

    def test_detect_multiple_changes(self):
        announcements = [
            "公司总经理辞职",
            "公司聘任李四为新任副总经理",
        ]
        results = detect_management_change(announcements)
        assert len(results) >= 2

    def test_no_management_change(self):
        announcements = ["公司发布季度财报", "公司召开股东大会"]
        results = detect_management_change(announcements)
        assert len(results) == 0

    def test_severity_levels(self):
        announcements = [
            "公司董事长辞职",       # high
            "公司副总裁退休",       # medium
            "公司财务总监代理CEO",  # low
        ]
        results = detect_management_change(announcements)
        severities = {r["keyword"]: r["severity"] for r in results}
        assert severities.get("辞职") == "high"
        assert severities.get("退休") == "medium"
        assert severities.get("代理") == "low"


class TestManagementChangeEdgeCases:
    """Edge cases for management change detection."""

    def test_empty_list(self):
        results = detect_management_change([])
        assert results == []

    def test_empty_strings_in_list(self):
        results = detect_management_change(["", "", ""])
        assert results == []

    def test_mixed_valid_and_empty(self):
        announcements = ["", "公司董事长离任", ""]
        results = detect_management_change(announcements)
        assert len(results) == 1
        assert results[0]["keyword"] == "离任"

    def test_deduplication(self):
        """Same text+keyword should not appear twice."""
        announcements = ["公司董事长辞职，总经理辞职"]
        results = detect_management_change(announcements)
        resignations = [r for r in results if r["keyword"] == "辞职"]
        assert len(resignations) == 1  # deduped on (text, keyword)
