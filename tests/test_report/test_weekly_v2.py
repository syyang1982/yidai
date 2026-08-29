"""
Tests for the enhanced weekly report generator v2.

Covers: report generation with mock data, KB section inclusion,
signal alerts section, and markdown validity.
"""

import os
from datetime import date, timedelta
from pathlib import Path

from src.data.store import YidaiStore
from src.report.weekly_v2 import (
    generate_report_v2,
    _render_signal_alerts,
    _render_kb_insights,
    _render_action_items,
    _render_anomaly_alerts,
    _next_grade_info,
)
from src.analysis.anomaly import AnomalyAlert
from src.knowledge.base import KnowledgeBase
from src.strategy.signal_tracker import SignalTracker


# ---------------------------------------------------------------------------
# Helpers — seed store, knowledge base, and signal tracker
# ---------------------------------------------------------------------------

def _seed_store(db_path: str) -> YidaiStore:
    """Create a store with sample companies, prices, and scores."""
    store = YidaiStore(db_path)
    prev_date = date.today() - timedelta(days=7)

    # Company A: BUY (strong)
    store.upsert_company({
        "ticker": "0700.HK", "name": "腾讯控股", "market": "HK",
        "currency": "HKD", "sector": "Technology", "notes": "",
    })
    store.upsert_price({
        "ticker": "0700.HK", "date": date.today(),
        "close_price": 380.0, "market_cap": 3_600_000_000_000,
        "pe_ratio": 22.0, "pb_ratio": 3.9, "ps_ratio": 5.5,
    })
    store.upsert_score({
        "ticker": "0700.HK", "date": prev_date,
        "profitability_score": 4, "health_score": 4, "cashflow_score": 4,
        "valuation_score": 3, "growth_score": 4, "ownership_score": 4,
        "strategy_score": 4, "total_score": 27, "grade": "B", "signal": "HOLD",
    })
    store.upsert_score({
        "ticker": "0700.HK", "date": date.today(),
        "profitability_score": 5, "health_score": 5, "cashflow_score": 5,
        "valuation_score": 4, "growth_score": 4, "ownership_score": 5,
        "strategy_score": 5, "total_score": 33, "grade": "A", "signal": "BUY",
    })

    # Company B: HOLD (near A boundary — 28/35)
    store.upsert_company({
        "ticker": "AAPL", "name": "Apple Inc.", "market": "US",
        "currency": "USD", "sector": "Technology", "notes": "",
    })
    store.upsert_price({
        "ticker": "AAPL", "date": date.today(),
        "close_price": 195.0, "market_cap": 3_000_000_000_000,
        "pe_ratio": 30.0, "pb_ratio": 50.0, "ps_ratio": 7.7,
    })
    store.upsert_score({
        "ticker": "AAPL", "date": date.today(),
        "profitability_score": 4, "health_score": 4, "cashflow_score": 4,
        "valuation_score": 4, "growth_score": 4, "ownership_score": 4,
        "strategy_score": 4, "total_score": 28, "grade": "B", "signal": "HOLD",
    })

    # Company C: REDUCE (deteriorating)
    store.upsert_company({
        "ticker": "WEAK.SZ", "name": "弱鸡科技", "market": "A",
        "currency": "CNY", "sector": "Industrials", "notes": "",
    })
    store.upsert_price({
        "ticker": "WEAK.SZ", "date": date.today(),
        "close_price": 3.5, "market_cap": 1_750_000_000,
        "pe_ratio": None, "pb_ratio": 3.5, "ps_ratio": 1.75,
    })
    store.upsert_score({
        "ticker": "WEAK.SZ", "date": prev_date,
        "profitability_score": 2, "health_score": 2, "cashflow_score": 1,
        "valuation_score": 2, "growth_score": 2, "ownership_score": 2,
        "strategy_score": 2, "total_score": 13, "grade": "D", "signal": "REDUCE",
    })
    store.upsert_score({
        "ticker": "WEAK.SZ", "date": date.today(),
        "profitability_score": 1, "health_score": 1, "cashflow_score": 0,
        "valuation_score": 2, "growth_score": 1, "ownership_score": 1,
        "strategy_score": 1, "total_score": 7, "grade": "F", "signal": "REDUCE",
    })

    return store


def _seed_knowledge_base(kb_dir: str) -> KnowledgeBase:
    """Create a KB with a company profile, lessons, and principles."""
    kb = KnowledgeBase(kb_dir)

    # Company profile
    kb.create_company_profile(
        "0700.HK", "腾讯控股", "HK", "Technology",
        thesis="社交+游戏双轮驱动，护城河宽广，估值合理。",
    )
    kb.add_risk("0700.HK", "游戏版号政策风险")
    kb.add_risk("0700.HK", "反垄断监管趋严")

    kb.create_company_profile(
        "AAPL", "Apple Inc.", "US", "Technology",
        thesis="生态闭环 + 服务收入增长，长期持有标的。",
    )

    # Lessons
    kb.add_lesson("估值不能只看PE，要结合行业特性", source_ticker="0700.HK", category="估值")
    kb.add_lesson("现金流是生命线，利润可以造假但现金流不会", source_ticker="", category="现金流")
    kb.add_lesson("高ROE不一定是好事，要看杠杆率", source_ticker="AAPL", category="其他")

    # Principles
    kb.add_principle("安全边际优先，宁可错过也不买贵")
    kb.add_principle("集中持有少数优质标的，分散不等于安全")

    return kb


def _seed_signal_tracker(db_path: str) -> SignalTracker:
    """Create a signal tracker with some records."""
    tracker = SignalTracker(db_path)

    tracker.record_signal(
        ticker="0700.HK",
        company_name="腾讯控股",
        signal_date=(date.today() - timedelta(days=30)).isoformat(),
        signal_type="BUY",
        company_state={"price": 350.0, "pe": 20.0, "revenue": 650e9, "net_income": 160e9},
        dimension_scores={"盈利": 5, "健康": 5, "现金流": 5, "估值": 4, "成长": 4, "股东": 5, "战略": 5},
        total_score=33,
        grade="A",
        analysis_details={},
    )

    tracker.record_signal(
        ticker="AAPL",
        company_name="Apple Inc.",
        signal_date=(date.today() - timedelta(days=60)).isoformat(),
        signal_type="HOLD",
        company_state={"price": 190.0, "pe": 29.0, "revenue": 390e9, "net_income": 100e9},
        dimension_scores={"盈利": 4, "健康": 4, "现金流": 4, "估值": 4, "成长": 4, "股东": 4, "战略": 4},
        total_score=28,
        grade="B",
        analysis_details={},
    )

    return tracker


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateReportV2:
    """Test report generation with mock data."""

    def test_report_file_created(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)

        assert Path(filepath).exists()
        assert filepath.endswith(".md")
        assert "weekly_v2_" in filepath

    def test_report_contains_header(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "意怠投资增强周报" in content
        assert "跟踪公司数" in content
        assert "信号汇总" in content

    def test_report_contains_all_companies(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "腾讯控股" in content
        assert "0700.HK" in content
        assert "Apple Inc." in content
        assert "AAPL" in content
        assert "弱鸡科技" in content

    def test_report_contains_scores(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "█" in content
        assert "░" in content
        assert "盈利能力" in content
        assert "七维评分" in content

    def test_report_contains_signals_and_grades(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "🟢" in content  # BUY
        assert "买入" in content
        assert "🔴" in content  # REDUCE
        assert "减仓" in content
        assert "评级" in content

    def test_report_contains_action_items(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "待办事项" in content

    def test_report_contains_disclaimer(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "不构成投资建议" in content
        assert "增强版 v2" in content

    def test_report_empty_db(self, tmp_path):
        db_path = str(tmp_path / "empty.duckdb")
        output_dir = str(tmp_path / "reports")
        YidaiStore(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert Path(filepath).exists()
        assert "意怠投资增强周报" in content

    def test_report_valid_markdown(self, tmp_path):
        """Report should be valid markdown: has headings, tables, etc."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        # Has at least one heading
        assert content.strip().startswith("# ")
        # Has table separator
        assert "|------" in content
        # No raw Python errors
        assert "Traceback" not in content
        assert "Error" not in content


class TestKBSectionInclusion:
    """Test that knowledge base data appears in the report."""

    def test_kb_thesis_in_report(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        kb_dir = str(tmp_path / "knowledge")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        _seed_knowledge_base(kb_dir)

        filepath = generate_report_v2(db_path, kb_dir=kb_dir, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "投资论点" in content
        assert "社交+游戏双轮驱动" in content

    def test_kb_risks_in_report(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        kb_dir = str(tmp_path / "knowledge")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        _seed_knowledge_base(kb_dir)

        filepath = generate_report_v2(db_path, kb_dir=kb_dir, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "风险因素" in content
        assert "游戏版号政策风险" in content

    def test_kb_insights_in_report(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        kb_dir = str(tmp_path / "knowledge")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        _seed_knowledge_base(kb_dir)

        filepath = generate_report_v2(db_path, kb_dir=kb_dir, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "知识库洞察" in content
        assert "经验教训" in content
        assert "投资原则" in content
        assert "安全边际优先" in content

    def test_kb_lessons_in_report(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        kb_dir = str(tmp_path / "knowledge")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        _seed_knowledge_base(kb_dir)

        filepath = generate_report_v2(db_path, kb_dir=kb_dir, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "估值不能只看PE" in content

    def test_report_without_kb(self, tmp_path):
        """Report should still work when KB is not available."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(
            db_path, kb_dir="/nonexistent", output_dir=output_dir,
        )
        content = Path(filepath).read_text(encoding="utf-8")

        assert "意怠投资增强周报" in content
        # KB insights section should still appear (with fallback message)
        assert "知识库洞察" in content


class TestSignalAlertsSection:
    """Test signal alerts section in the report."""

    def test_signal_alerts_section_exists(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        signal_db_path = str(tmp_path / "signals.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        _seed_signal_tracker(signal_db_path)

        filepath = generate_report_v2(
            db_path, signal_db_path=signal_db_path, output_dir=output_dir,
        )
        content = Path(filepath).read_text(encoding="utf-8")

        assert "信号预警" in content

    def test_signal_tracker_signals_in_report(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        signal_db_path = str(tmp_path / "signals.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        _seed_signal_tracker(signal_db_path)

        filepath = generate_report_v2(
            db_path, signal_db_path=signal_db_path, output_dir=output_dir,
        )
        content = Path(filepath).read_text(encoding="utf-8")

        assert "新信号" in content
        assert "腾讯控股" in content

    def test_pending_reviews_in_report(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        signal_db_path = str(tmp_path / "signals.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        tracker = _seed_signal_tracker(signal_db_path)

        filepath = generate_report_v2(
            db_path, signal_db_path=signal_db_path, output_dir=output_dir,
        )
        content = Path(filepath).read_text(encoding="utf-8")

        # Should show pending reviews
        assert "待回顾" in content

    def test_report_without_signal_tracker(self, tmp_path):
        """Report should work without signal tracker."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(
            db_path, signal_db_path="/nonexistent", output_dir=output_dir,
        )
        content = Path(filepath).read_text(encoding="utf-8")

        assert "信号预警" in content
        # Should show fallback message
        assert "无新信号" in content


class TestReportMarkdownValidity:
    """Test that the generated report is valid markdown."""

    def test_has_headings(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        # Must start with a top-level heading
        assert content.strip().startswith("# ")
        # Has multiple heading levels
        assert "## " in content

    def test_has_tables(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report_v2(db_path, output_dir=output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        # Table header separator
        assert "|------" in content
        # Table cells
        assert "| " in content

    def test_no_python_errors(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        kb_dir = str(tmp_path / "knowledge")
        signal_db_path = str(tmp_path / "signals.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()
        _seed_knowledge_base(kb_dir)
        _seed_signal_tracker(signal_db_path)

        filepath = generate_report_v2(
            db_path, kb_dir=kb_dir, signal_db_path=signal_db_path,
            output_dir=output_dir,
        )
        content = Path(filepath).read_text(encoding="utf-8")

        for bad in ["Traceback", "Error:", "Exception", "TypeError", "KeyError"]:
            assert bad not in content, f"Found '{bad}' in report content"


class TestNextGradeInfo:
    """Test the grade boundary helper."""

    def test_near_a(self):
        info = _next_grade_info(32)
        assert info is not None
        assert info["next_grade"] == "A"
        assert info["gap"] == 1

    def test_at_max(self):
        info = _next_grade_info(35)
        assert info is None

    def test_far_from_next(self):
        info = _next_grade_info(10)
        assert info is not None
        assert info["gap"] > 3


class TestRenderHelpers:
    """Test individual section renderers."""

    def test_render_signal_alerts_empty(self):
        result = _render_signal_alerts([], [], [])
        assert "无新信号" in result

    def test_render_signal_alerts_with_data(self):
        signals = [{
            "ticker": "0700.HK", "company_name": "腾讯",
            "signal_type": "BUY", "signal_date": "2025-01-01",
            "total_score": 33, "grade": "A",
        }]
        result = _render_signal_alerts(signals, [], [])
        assert "新信号" in result
        assert "腾讯" in result

    def test_render_kb_insights_empty(self):
        result = _render_kb_insights(None, None)
        assert "知识库洞察" in result
        assert "暂无数据" in result

    def test_render_action_items_deteriorating(self):
        det = [{"name": "测试公司", "ticker": "TEST", "prev_total": 20, "curr_total": 15}]
        result = _render_action_items(0, det, [])
        assert "评分恶化" in result
        assert "20→15" in result

    def test_render_action_items_near_boundary(self):
        nb = [{
            "name": "测试公司", "ticker": "TEST", "total": 28,
            "next_grade_info": {"next_grade": "A", "threshold": 29, "gap": 1},
        }]
        result = _render_action_items(0, [], nb)
        assert "接近评级边界" in result
        assert "距 A 仅差 1 分" in result


class TestRenderAnomalyAlerts:
    """Test the anomaly alerts renderer."""

    def test_render_anomaly_alerts_empty(self):
        """No alerts should return empty string."""
        result = _render_anomaly_alerts([])
        assert result == ""

    def test_render_anomaly_alerts_high_only(self):
        """HIGH alerts should appear under the HIGH heading."""
        alerts = [
            AnomalyAlert(
                rule_id="W1.1.1",
                rule_name="应收账款 vs 营收增速",
                severity="HIGH",
                emoji="🔴",
                ticker="0700.HK",
                company_name="腾讯控股",
                period="2024-12-31",
                detail="连续2期应收账款增速超过营收增速10%以上",
                metrics={"consecutive_periods": 2},
            ),
        ]
        result = _render_anomaly_alerts(alerts)
        assert "财务异常预警" in result
        assert "HIGH" in result
        assert "建议减仓" in result
        assert "腾讯控股" in result
        assert "W1.1.1" in result
        assert "应收账款" in result
        # No MEDIUM section
        assert "MEDIUM" not in result

    def test_render_anomaly_alerts_grouped_by_severity(self):
        """Alerts should be grouped: HIGH first, then MEDIUM."""
        alerts = [
            AnomalyAlert(
                rule_id="W1.1.2",
                rule_name="存货周转率趋势",
                severity="MEDIUM",
                emoji="🟡",
                ticker="AAPL",
                company_name="Apple Inc.",
                period="2024-12-31",
                detail="存货周转率连续3期下降",
                metrics={"declining_periods": 3},
            ),
            AnomalyAlert(
                rule_id="W1.1.1",
                rule_name="应收账款 vs 营收增速",
                severity="HIGH",
                emoji="🔴",
                ticker="0700.HK",
                company_name="腾讯控股",
                period="2024-12-31",
                detail="连续2期应收账款增速超过营收增速10%以上",
                metrics={"consecutive_periods": 2},
            ),
        ]
        result = _render_anomaly_alerts(alerts)
        # HIGH section should come before MEDIUM
        high_pos = result.index("HIGH")
        medium_pos = result.index("MEDIUM")
        assert high_pos < medium_pos
        # Both companies present
        assert "腾讯控股" in result
        assert "Apple Inc." in result
        # Section headings
        assert "建议减仓" in result
        assert "标记跟踪" in result

    def test_render_anomaly_alerts_with_metrics(self):
        """Metrics should be rendered as key=value pairs."""
        alerts = [
            AnomalyAlert(
                rule_id="W1.1.4",
                rule_name="短贷长投",
                severity="HIGH",
                emoji="🔴",
                ticker="TEST.HK",
                company_name="测试公司",
                period="2024-12-31",
                detail="短期借款增长50%",
                metrics={"short_loan_growth": 50.0, "short_loan_ratio": 8.5},
            ),
        ]
        result = _render_anomaly_alerts(alerts)
        assert "short_loan_growth=50.0" in result
        assert "short_loan_ratio=8.5" in result

    def test_render_anomaly_alerts_has_separator(self):
        """Output should end with a horizontal rule separator."""
        alerts = [
            AnomalyAlert(
                rule_id="W1.1.3",
                rule_name="利润质量",
                severity="MEDIUM",
                emoji="🟡",
                ticker="TEST.HK",
                company_name="测试公司",
                period="2024-12-31",
                detail="利润质量差",
                metrics={},
            ),
        ]
        result = _render_anomaly_alerts(alerts)
        assert "---" in result
