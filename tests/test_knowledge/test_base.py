"""Tests for the KnowledgeBase investment knowledge management system.

All user-facing text in Chinese. Uses pytest with tmp_path.
"""

from __future__ import annotations

import os
import re

import pytest

from src.knowledge.base import KnowledgeBase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kb(tmp_path):
    """Create a KnowledgeBase with a temporary directory."""
    return KnowledgeBase(base_dir=str(tmp_path))


@pytest.fixture
def kb_with_xiaomi(kb):
    """KnowledgeBase with a Xiaomi company profile pre-created."""
    kb.create_company_profile(
        ticker="01810.HK",
        name="小米集团",
        market="HK",
        sector="消费电子",
        thesis="智能手机+AIoT双轮驱动，长期看好生态闭环",
    )
    return kb


# ---------------------------------------------------------------------------
# TestCreateProfile
# ---------------------------------------------------------------------------

class TestCreateProfile:
    def test_file_created(self, kb):
        path = kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        assert os.path.exists(path)
        assert path.endswith("01810.HK.md")

    def test_directory_structure(self, kb):
        kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        assert os.path.isdir(os.path.join(kb.base_dir, "companies"))

    def test_template_correct(self, kb):
        kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        content = kb._read_markdown(kb._company_path("01810.HK"))
        assert "小米集团 (01810.HK)" in content
        assert "## 基本信息" in content
        assert "## 投资论点 (Thesis)" in content
        assert "## 当前评分" in content
        assert "## 历史变化" in content
        assert "## 复盘记录" in content
        assert "## 关键指标追踪" in content
        assert "## 风险因素" in content
        assert "## 用户反思" in content
        assert "- 市场: HK" in content
        assert "- 行业: 消费电子" in content

    def test_create_with_thesis(self, kb):
        path = kb.create_company_profile(
            "0700.HK", "腾讯控股", "HK", "互联网",
            thesis="社交+游戏生态，长期价值",
        )
        content = kb._read_markdown(path)
        assert "社交+游戏生态，长期价值" in content

    def test_create_multiple(self, kb):
        kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        kb.create_company_profile("0700.HK", "腾讯控股", "HK", "互联网")
        companies = kb.list_companies()
        assert len(companies) == 2


# ---------------------------------------------------------------------------
# TestUpdateScores
# ---------------------------------------------------------------------------

class TestUpdateScores:
    def test_scores_updated(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {
            "profitability_score": 4,
            "health_score": 3,
            "cashflow_score": 4,
            "valuation_score": 3,
            "growth_score": 4,
            "ownership_score": 5,
            "strategy_score": 4,
        })
        profile = kb.get_company_profile("01810.HK")
        assert profile["scores"]["盈利"]["score"] == 4
        assert profile["total"] == 27
        assert profile["grade"] == "B"

    def test_trends_detected_up(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        # Initial: all 0
        kb.update_company_scores("01810.HK", {
            "profitability_score": 3,
            "health_score": 2,
            "cashflow_score": 3,
            "valuation_score": 2,
            "growth_score": 3,
            "ownership_score": 4,
            "strategy_score": 3,
        })
        profile = kb.get_company_profile("01810.HK")
        # All should be ↑ since initial was 0
        assert profile["scores"]["盈利"]["trend"] == "↑"
        assert profile["scores"]["健康"]["trend"] == "↑"

    def test_trends_detected_down(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        # First update
        kb.update_company_scores("01810.HK", {
            "profitability_score": 4,
            "health_score": 4,
            "cashflow_score": 4,
            "valuation_score": 4,
            "growth_score": 4,
            "ownership_score": 5,
            "strategy_score": 4,
        })
        # Second update: lower scores
        kb.update_company_scores("01810.HK", {
            "profitability_score": 2,
            "health_score": 3,
            "cashflow_score": 4,
            "valuation_score": 5,
            "growth_score": 3,
            "ownership_score": 5,
            "strategy_score": 4,
        })
        profile = kb.get_company_profile("01810.HK")
        assert profile["scores"]["盈利"]["trend"] == "↓"
        assert profile["scores"]["健康"]["trend"] == "↓"
        assert profile["scores"]["估值"]["trend"] == "↑"
        assert profile["scores"]["现金流"]["trend"] == "→"

    def test_trends_detected_stable(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {"profitability_score": 3})
        kb.update_company_scores("01810.HK", {"profitability_score": 3})
        profile = kb.get_company_profile("01810.HK")
        assert profile["scores"]["盈利"]["trend"] == "→"

    def test_history_row_added(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {"profitability_score": 3}, event_date="2025-01-01")
        kb.update_company_scores("01810.HK", {"profitability_score": 4}, event_date="2025-02-01")
        profile = kb.get_company_profile("01810.HK")
        assert len(profile["history"]) >= 2

    def test_chinese_key_format(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {"盈利": 4, "健康": 3})
        profile = kb.get_company_profile("01810.HK")
        assert profile["scores"]["盈利"]["score"] == 4
        assert profile["scores"]["健康"]["score"] == 3


# ---------------------------------------------------------------------------
# TestUpdateFinancials
# ---------------------------------------------------------------------------

class TestUpdateFinancials:
    def test_metrics_updated(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_financials("01810.HK", {
            "营收": "3200亿",
            "净利": "240亿",
            "ROE": "18.5%",
        })
        profile = kb.get_company_profile("01810.HK")
        financials = {f["指标"]: f["本期"] for f in profile["financials"]}
        assert financials["营收"] == "3200亿"
        assert financials["净利"] == "240亿"

    def test_changes_detected(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_financials("01810.HK", {"营收": "100"}, event_date="2025-01-01")
        kb.update_company_financials("01810.HK", {"营收": "120"}, event_date="2025-06-01")
        profile = kb.get_company_profile("01810.HK")
        # Find the row for 营收
        for f in profile["financials"]:
            if f["指标"] == "营收":
                assert "+20.0%" in f["变化"]
                break


# ---------------------------------------------------------------------------
# TestAddReview
# ---------------------------------------------------------------------------

class TestAddReview:
    def test_review_entry_added(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.add_review(
            "01810.HK",
            "做对了: 长期持有\n做错了: 没有在高位适当减仓\n教训: 需要关注估值信号",
            event_date="2025-06-01",
        )
        profile = kb.get_company_profile("01810.HK")
        assert len(profile["reviews"]) >= 1
        assert "2025-06-01" in profile["reviews"][0]["date"]
        assert "长期持有" in profile["reviews"][0]["content"]

    def test_multiple_reviews(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.add_review("01810.HK", "第一次复盘", event_date="2025-01-01")
        kb.add_review("01810.HK", "第二次复盘", event_date="2025-06-01")
        profile = kb.get_company_profile("01810.HK")
        assert len(profile["reviews"]) >= 2


# ---------------------------------------------------------------------------
# TestThesisAndRisks
# ---------------------------------------------------------------------------

class TestThesisAndRisks:
    def test_thesis_updated(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.add_thesis("01810.HK", "更新后的投资论点：看好小米汽车业务")
        profile = kb.get_company_profile("01810.HK")
        assert "小米汽车" in profile["thesis"]

    def test_risk_added(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.add_risk("01810.HK", "手机市场竞争加剧")
        kb.add_risk("01810.HK", "汽车业务亏损扩大")
        profile = kb.get_company_profile("01810.HK")
        assert "手机市场竞争加剧" in profile["risks"]
        assert "汽车业务亏损扩大" in profile["risks"]

    def test_reflection_added(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.add_reflection("01810.HK", "需要更关注管理层的战略执行力")
        profile = kb.get_company_profile("01810.HK")
        assert "管理层" in profile["reflection"]


# ---------------------------------------------------------------------------
# TestLessons
# ---------------------------------------------------------------------------

class TestLessons:
    def test_add_lesson(self, kb):
        kb.add_lesson("不要追高买入", source_ticker="01810.HK", category="心理")
        lessons = kb.get_lessons()
        assert len(lessons) >= 1
        assert lessons[0]["content"] == "不要追高买入"
        assert lessons[0]["source"] == "01810.HK"
        assert lessons[0]["category"] == "心理"

    def test_category_filter(self, kb):
        kb.add_lesson("估值过高时要谨慎", category="估值")
        kb.add_lesson("现金流比利润更重要", category="现金流")
        kb.add_lesson("保持耐心", category="心理")

        val_lessons = kb.get_lessons(category="估值")
        assert len(val_lessons) == 1
        assert "估值" in val_lessons[0]["content"]

        psych_lessons = kb.get_lessons(category="心理")
        assert len(psych_lessons) == 1
        assert "耐心" in psych_lessons[0]["content"]

    def test_invalid_category_defaults(self, kb):
        kb.add_lesson("测试", category="无效类别")
        lessons = kb.get_lessons()
        assert lessons[0]["category"] == "其他"

    def test_multiple_lessons(self, kb):
        kb.add_lesson("第一课", category="估值")
        kb.add_lesson("第二课", category="增长")
        kb.add_lesson("第三课", category="风险管理")
        lessons = kb.get_lessons()
        assert len(lessons) == 3


# ---------------------------------------------------------------------------
# TestPrinciples
# ---------------------------------------------------------------------------

class TestPrinciples:
    def test_add_principle(self, kb):
        kb.add_principle(
            "只买自己能理解的公司",
            evidence="2024年投资XX公司亏损，因为不了解其商业模式",
        )
        principles = kb.get_principles()
        assert len(principles) >= 1
        assert "理解" in principles[0]["principle"]
        assert "商业模式" in principles[0]["evidence"]

    def test_principle_without_evidence(self, kb):
        kb.add_principle("长期持有优质公司")
        principles = kb.get_principles()
        assert principles[0]["evidence"] == ""

    def test_multiple_principles(self, kb):
        kb.add_principle("原则一", evidence="依据一")
        kb.add_principle("原则二", evidence="依据二")
        principles = kb.get_principles()
        assert len(principles) == 2


# ---------------------------------------------------------------------------
# TestJournal
# ---------------------------------------------------------------------------

class TestJournal:
    def test_add_entry(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {
            "profitability_score": 4,
            "health_score": 3,
            "cashflow_score": 4,
            "valuation_score": 3,
            "growth_score": 4,
            "ownership_score": 5,
            "strategy_score": 4,
        })
        kb.add_journal_entry(
            "01810.HK", "增持", "业绩超预期", event_date="2025-06-01",
        )
        entries = kb.get_journal()
        assert len(entries) >= 1
        assert entries[0]["ticker"] == "01810.HK"
        assert entries[0]["action"] == "增持"
        assert "业绩超预期" in entries[0]["reason"]

    def test_ticker_filter(self, kb):
        kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        kb.create_company_profile("0700.HK", "腾讯控股", "HK", "互联网")
        kb.add_journal_entry("01810.HK", "买入", "理由一", event_date="2025-01-01")
        kb.add_journal_entry("0700.HK", "观察", "理由二", event_date="2025-02-01")
        kb.add_journal_entry("01810.HK", "增持", "理由三", event_date="2025-03-01")

        xiaomi_entries = kb.get_journal(ticker="01810.HK")
        assert len(xiaomi_entries) == 2
        tencent_entries = kb.get_journal(ticker="0700.HK")
        assert len(tencent_entries) == 1

    def test_journal_without_company_profile(self, kb):
        """Journal entry for non-existent company should still work."""
        kb.add_journal_entry("UNKNOWN", "观察", "测试", event_date="2025-01-01")
        entries = kb.get_journal()
        assert len(entries) == 1
        assert "无数据" in entries[0]["scores"]


# ---------------------------------------------------------------------------
# TestCompanySummary
# ---------------------------------------------------------------------------

class TestCompanySummary:
    def test_summary_generation(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {
            "profitability_score": 4,
            "health_score": 3,
            "cashflow_score": 4,
            "valuation_score": 3,
            "growth_score": 4,
            "ownership_score": 5,
            "strategy_score": 4,
        })
        kb.add_risk("01810.HK", "手机市场竞争")
        summary = kb.generate_company_summary("01810.HK")
        assert "小米集团" in summary
        assert "01810.HK" in summary
        assert "总分" in summary
        assert "风险因素" in summary
        assert "手机市场竞争" in summary

    def test_summary_with_history(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {"profitability_score": 3}, event_date="2025-01-01")
        kb.update_company_scores("01810.HK", {"profitability_score": 4}, event_date="2025-06-01")
        summary = kb.generate_company_summary("01810.HK")
        assert "近期变化" in summary


# ---------------------------------------------------------------------------
# TestKbSummary
# ---------------------------------------------------------------------------

class TestKbSummary:
    def test_overview_generation(self, kb):
        kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        kb.create_company_profile("0700.HK", "腾讯控股", "HK", "互联网")
        kb.add_lesson("测试教训", category="估值")
        kb.add_principle("测试原则", evidence="测试依据")

        summary = kb.generate_kb_summary()
        assert "知识库总览" in summary
        assert "小米集团" in summary
        assert "腾讯控股" in summary
        assert "2家" in summary
        assert "1条" in summary
        assert "测试教训" in summary
        assert "测试原则" in summary

    def test_empty_kb_summary(self, kb):
        summary = kb.generate_kb_summary()
        assert "0家" in summary
        assert "0条" in summary


# ---------------------------------------------------------------------------
# TestGetCompanyProfile
# ---------------------------------------------------------------------------

class TestGetCompanyProfile:
    def test_parse_all_sections(self, kb_with_xiaomi):
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {
            "profitability_score": 4,
            "health_score": 3,
            "cashflow_score": 4,
            "valuation_score": 3,
            "growth_score": 4,
            "ownership_score": 5,
            "strategy_score": 4,
        })
        kb.update_company_financials("01810.HK", {"营收": "3200亿", "净利": "240亿"})
        kb.add_risk("01810.HK", "测试风险")
        kb.add_reflection("01810.HK", "测试反思")
        kb.add_review("01810.HK", "测试复盘", event_date="2025-06-01")

        profile = kb.get_company_profile("01810.HK")
        assert profile["ticker"] == "01810.HK"
        assert profile["name"] == "小米集团"
        assert profile["market"] == "HK"
        assert profile["sector"] == "消费电子"
        assert "智能手机" in profile["thesis"]
        assert profile["total"] == 27
        assert profile["grade"] == "B"
        assert len(profile["risks"]) >= 1
        assert "测试反思" in profile["reflection"]
        assert len(profile["reviews"]) >= 1
        assert len(profile["financials"]) >= 1

    def test_missing_company_raises(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.get_company_profile("NONEXISTENT")


# ---------------------------------------------------------------------------
# TestListCompanies
# ---------------------------------------------------------------------------

class TestListCompanies:
    def test_multiple_companies(self, kb):
        kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        kb.create_company_profile("0700.HK", "腾讯控股", "HK", "互联网")
        kb.update_company_scores("01810.HK", {
            "profitability_score": 4,
            "health_score": 3,
            "cashflow_score": 4,
            "valuation_score": 3,
            "growth_score": 4,
            "ownership_score": 5,
            "strategy_score": 4,
        })
        companies = kb.list_companies()
        assert len(companies) == 2
        # Should be sorted by filename
        tickers = [c["ticker"] for c in companies]
        assert "01810.HK" in tickers
        assert "0700.HK" in tickers

    def test_empty_list(self, kb):
        companies = kb.list_companies()
        assert len(companies) == 0


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_missing_file_raises(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.update_company_scores("NONEXISTENT", {"profitability_score": 3})

    def test_missing_file_risk_raises(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.add_risk("NONEXISTENT", "风险")

    def test_missing_file_review_raises(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.add_review("NONEXISTENT", "复盘")

    def test_missing_file_thesis_raises(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.add_thesis("NONEXISTENT", "论点")

    def test_missing_file_reflection_raises(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.add_reflection("NONEXISTENT", "反思")

    def test_missing_file_financials_raises(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.update_company_financials("NONEXISTENT", {"营收": "100"})

    def test_empty_profile_scores(self, kb_with_xiaomi):
        """Update scores with empty dict should not crash."""
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {})
        profile = kb.get_company_profile("01810.HK")
        assert profile["total"] == 0

    def test_duplicate_score_updates(self, kb_with_xiaomi):
        """Multiple score updates should accumulate in history."""
        kb = kb_with_xiaomi
        kb.update_company_scores("01810.HK", {"profitability_score": 3}, event_date="2025-01-01")
        kb.update_company_scores("01810.HK", {"profitability_score": 3}, event_date="2025-02-01")
        kb.update_company_scores("01810.HK", {"profitability_score": 3}, event_date="2025-03-01")
        profile = kb.get_company_profile("01810.HK")
        assert len(profile["history"]) >= 3

    def test_init_creates_stub_files(self, tmp_path):
        """KnowledgeBase init should create lessons.md, principles.md, journal.md."""
        base_dir = str(tmp_path / "test_kb")
        kb = KnowledgeBase(base_dir=base_dir)
        assert os.path.exists(os.path.join(base_dir, "lessons.md"))
        assert os.path.exists(os.path.join(base_dir, "principles.md"))
        assert os.path.exists(os.path.join(base_dir, "journal.md"))
        assert os.path.isdir(os.path.join(base_dir, "companies"))

    def test_company_path_format(self, kb):
        path = kb._company_path("01810.HK")
        assert path.endswith("companies/01810.HK.md")


# ---------------------------------------------------------------------------
# TestIntegration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, kb):
        """Full lifecycle: create → update → review → summarize."""
        # 1. Create profile
        path = kb.create_company_profile(
            "01810.HK", "小米集团", "HK", "消费电子",
            thesis="智能手机+AIoT双轮驱动",
        )
        assert os.path.exists(path)

        # 2. Update scores
        kb.update_company_scores("01810.HK", {
            "profitability_score": 3,
            "health_score": 3,
            "cashflow_score": 3,
            "valuation_score": 3,
            "growth_score": 3,
            "ownership_score": 4,
            "strategy_score": 3,
        }, event_date="2025-01-01")

        # 3. Update financials
        kb.update_company_financials("01810.HK", {
            "营收": "3200亿",
            "净利": "240亿",
            "ROE": "18.5%",
        }, event_date="2025-01-01")

        # 4. Add risks
        kb.add_risk("01810.HK", "手机市场竞争加剧")
        kb.add_risk("01810.HK", "汽车业务初期亏损")

        # 5. Update scores again (simulate progress)
        kb.update_company_scores("01810.HK", {
            "profitability_score": 4,
            "health_score": 3,
            "cashflow_score": 4,
            "valuation_score": 4,
            "growth_score": 4,
            "ownership_score": 5,
            "strategy_score": 4,
        }, event_date="2025-06-01")

        # 6. Add review
        kb.add_review(
            "01810.HK",
            "做对了: 坚持持有\n做错了: 没有在低位加仓\n教训: 低估了管理层执行力",
            event_date="2025-06-01",
        )

        # 7. Add journal entries
        kb.add_journal_entry("01810.HK", "初始建仓", "看好长期生态", event_date="2025-01-01")
        kb.add_journal_entry("01810.HK", "增持", "业绩超预期", event_date="2025-06-01")

        # 8. Add lessons
        kb.add_lesson("生态型公司要看整体而非单业务线", source_ticker="01810.HK", category="增长")

        # 9. Add principles
        kb.add_principle("长期持有生态型平台公司", evidence="小米案例证明生态壁垒")

        # 10. Add reflection
        kb.add_reflection("01810.HK", "需要更关注汽车业务的进展节奏")

        # --- Verify everything ---

        # Profile
        profile = kb.get_company_profile("01810.HK")
        assert profile["name"] == "小米集团"
        assert profile["total"] == 28
        assert profile["grade"] == "B"
        assert len(profile["history"]) >= 2
        assert len(profile["reviews"]) >= 1
        assert len(profile["risks"]) == 2
        assert "管理层执行力" in profile["reviews"][0]["content"]
        assert "汽车" in profile["reflection"]

        # Trends: profitability went from 3→4 (↑), health stayed 3 (→)
        assert profile["scores"]["盈利"]["trend"] == "↑"
        assert profile["scores"]["健康"]["trend"] == "→"

        # Journal
        journal = kb.get_journal(ticker="01810.HK")
        assert len(journal) == 2
        assert journal[0]["action"] == "初始建仓"
        assert journal[1]["action"] == "增持"

        # Lessons
        lessons = kb.get_lessons()
        assert len(lessons) >= 1
        assert lessons[0]["source"] == "01810.HK"

        # Principles
        principles = kb.get_principles()
        assert len(principles) >= 1

        # Company summary
        summary = kb.generate_company_summary("01810.HK")
        assert "小米集团" in summary
        assert "风险因素" in summary
        assert "手机市场竞争" in summary

        # KB summary
        kb_summary = kb.generate_kb_summary()
        assert "小米集团" in kb_summary
        assert "1家" in kb_summary

        # List companies
        companies = kb.list_companies()
        assert len(companies) == 1
        assert companies[0]["ticker"] == "01810.HK"

    def test_multi_company_lifecycle(self, kb):
        """Test with multiple companies."""
        kb.create_company_profile("01810.HK", "小米集团", "HK", "消费电子")
        kb.create_company_profile("0700.HK", "腾讯控股", "HK", "互联网")
        kb.create_company_profile("600519.SS", "贵州茅台", "A", "白酒")

        # Update scores for each
        for ticker, prof_score in [("01810.HK", 4), ("0700.HK", 3), ("600519.SS", 5)]:
            kb.update_company_scores(ticker, {
                "profitability_score": prof_score,
                "health_score": 4,
                "cashflow_score": 4,
                "valuation_score": 3,
                "growth_score": 3,
                "ownership_score": 4,
                "strategy_score": 4,
            })

        companies = kb.list_companies()
        assert len(companies) == 3

        # Cross-company lesson
        kb.add_lesson("多元化持仓降低风险", category="风险管理")
        lessons = kb.get_lessons(category="风险管理")
        assert len(lessons) == 1

        # KB summary
        summary = kb.generate_kb_summary()
        assert "3家" in summary
        assert "小米集团" in summary
        assert "腾讯控股" in summary
        assert "贵州茅台" in summary
