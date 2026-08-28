"""Tests for the weekly report generator."""

from datetime import date, timedelta
from pathlib import Path

from src.data.store import YidaiStore
from src.report.weekly import (
    format_score_bar,
    format_signal_emoji,
    generate_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_store(db_path: str) -> YidaiStore:
    """Create a store with sample companies, financials, prices, and scores."""
    store = YidaiStore(db_path)

    # --- Company A: strong BUY ---
    store.upsert_company({
        "ticker": "0700.HK",
        "name": "腾讯控股",
        "market": "HK",
        "currency": "HKD",
        "sector": "Technology",
        "notes": "",
    })
    store.upsert_financial({
        "ticker": "0700.HK",
        "period": "FY2023",
        "report_date": date(2023, 12, 31),
        "revenue": 600_000_000_000,
        "gross_profit": 280_000_000_000,
        "net_income": 150_000_000_000,
        "operating_income": 170_000_000_000,
        "total_assets": 1_600_000_000_000,
        "total_liabilities": 750_000_000_000,
        "total_equity": 850_000_000_000,
        "current_assets": 560_000_000_000,
        "current_liabilities": 390_000_000_000,
        "interest_bearing_debt": 240_000_000_000,
        "operating_cash_flow": 210_000_000_000,
        "capex": -45_000_000_000,
        "free_cash_flow": 165_000_000_000,
        "shares_outstanding": 9_500_000_000,
        "eps": 15.8,
    })
    store.upsert_financial({
        "ticker": "0700.HK",
        "period": "FY2024",
        "report_date": date(2024, 12, 31),
        "revenue": 650_000_000_000,
        "gross_profit": 310_000_000_000,
        "net_income": 160_000_000_000,
        "operating_income": 185_000_000_000,
        "total_assets": 1_700_000_000_000,
        "total_liabilities": 780_000_000_000,
        "total_equity": 920_000_000_000,
        "current_assets": 600_000_000_000,
        "current_liabilities": 410_000_000_000,
        "interest_bearing_debt": 250_000_000_000,
        "operating_cash_flow": 230_000_000_000,
        "capex": -50_000_000_000,
        "free_cash_flow": 180_000_000_000,
        "shares_outstanding": 9_500_000_000,
        "eps": 16.8,
    })
    store.upsert_price({
        "ticker": "0700.HK",
        "date": date.today(),
        "close_price": 380.0,
        "market_cap": 3_600_000_000_000,
        "pe_ratio": 22.0,
        "pb_ratio": 3.9,
        "ps_ratio": 5.5,
    })

    # Previous week score (for change detection)
    prev_date = date.today() - timedelta(days=7)
    store.upsert_score({
        "ticker": "0700.HK",
        "date": prev_date,
        "profitability_score": 4,
        "health_score": 4,
        "cashflow_score": 4,
        "valuation_score": 3,
        "growth_score": 4,
        "ownership_score": 4,
        "strategy_score": 4,
        "total_score": 27,
        "grade": "B",
        "signal": "HOLD",
    })

    # Current score
    store.upsert_score({
        "ticker": "0700.HK",
        "date": date.today(),
        "profitability_score": 5,
        "health_score": 5,
        "cashflow_score": 5,
        "valuation_score": 4,
        "growth_score": 4,
        "ownership_score": 5,
        "strategy_score": 5,
        "total_score": 33,
        "grade": "A",
        "signal": "BUY",
    })

    # --- Company B: HOLD ---
    store.upsert_company({
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "market": "US",
        "currency": "USD",
        "sector": "Technology",
        "notes": "",
    })
    store.upsert_financial({
        "ticker": "AAPL",
        "period": "FY2024",
        "report_date": date(2024, 9, 30),
        "revenue": 390_000_000_000,
        "gross_profit": 180_000_000_000,
        "net_income": 100_000_000_000,
        "operating_income": 120_000_000_000,
        "total_assets": 350_000_000_000,
        "total_liabilities": 290_000_000_000,
        "total_equity": 60_000_000_000,
        "current_assets": 140_000_000_000,
        "current_liabilities": 120_000_000_000,
        "interest_bearing_debt": 100_000_000_000,
        "operating_cash_flow": 110_000_000_000,
        "capex": -10_000_000_000,
        "free_cash_flow": 100_000_000_000,
        "shares_outstanding": 15_000_000_000,
        "eps": 6.67,
    })
    store.upsert_price({
        "ticker": "AAPL",
        "date": date.today(),
        "close_price": 195.0,
        "market_cap": 3_000_000_000_000,
        "pe_ratio": 30.0,
        "pb_ratio": 50.0,
        "ps_ratio": 7.7,
    })
    store.upsert_score({
        "ticker": "AAPL",
        "date": date.today(),
        "profitability_score": 4,
        "health_score": 3,
        "cashflow_score": 4,
        "valuation_score": 2,
        "growth_score": 3,
        "ownership_score": 4,
        "strategy_score": 4,
        "total_score": 24,
        "grade": "B",
        "signal": "HOLD",
    })

    # --- Company C: REDUCE (weak) ---
    store.upsert_company({
        "ticker": "WEAK.SZ",
        "name": "弱鸡科技",
        "market": "A",
        "currency": "CNY",
        "sector": "Industrials",
        "notes": "",
    })
    store.upsert_financial({
        "ticker": "WEAK.SZ",
        "period": "FY2024",
        "report_date": date(2024, 12, 31),
        "revenue": 1_000_000_000,
        "gross_profit": 200_000_000,
        "net_income": -50_000_000,
        "operating_income": -30_000_000,
        "total_assets": 5_000_000_000,
        "total_liabilities": 4_500_000_000,
        "total_equity": 500_000_000,
        "current_assets": 1_000_000_000,
        "current_liabilities": 2_000_000_000,
        "interest_bearing_debt": 3_000_000_000,
        "operating_cash_flow": -100_000_000,
        "capex": -200_000_000,
        "free_cash_flow": -300_000_000,
        "shares_outstanding": 500_000_000,
        "eps": -0.1,
    })
    store.upsert_price({
        "ticker": "WEAK.SZ",
        "date": date.today(),
        "close_price": 3.5,
        "market_cap": 1_750_000_000,
        "pe_ratio": None,  # negative earnings
        "pb_ratio": 3.5,
        "ps_ratio": 1.75,
    })

    # Previous week score for WEAK.SZ (was HOLD, now REDUCE)
    store.upsert_score({
        "ticker": "WEAK.SZ",
        "date": prev_date,
        "profitability_score": 2,
        "health_score": 2,
        "cashflow_score": 1,
        "valuation_score": 2,
        "growth_score": 2,
        "ownership_score": 2,
        "strategy_score": 2,
        "total_score": 13,
        "grade": "D",
        "signal": "REDUCE",
    })

    store.upsert_score({
        "ticker": "WEAK.SZ",
        "date": date.today(),
        "profitability_score": 1,
        "health_score": 1,
        "cashflow_score": 0,
        "valuation_score": 2,
        "growth_score": 1,
        "ownership_score": 1,
        "strategy_score": 1,
        "total_score": 7,
        "grade": "F",
        "signal": "REDUCE",
    })

    return store


# ---------------------------------------------------------------------------
# Tests for utility functions
# ---------------------------------------------------------------------------

class TestFormatScoreBar:
    def test_full_score(self):
        assert format_score_bar(5) == "█████"

    def test_zero_score(self):
        assert format_score_bar(0) == "░░░░░"

    def test_partial_score(self):
        assert format_score_bar(3) == "███░░"

    def test_custom_max(self):
        assert format_score_bar(2, max_score=10) == "██░░░░░░░░"

    def test_clamp_over(self):
        assert format_score_bar(10, max_score=5) == "█████"

    def test_clamp_negative(self):
        assert format_score_bar(-1) == "░░░░░"


class TestFormatSignalEmoji:
    def test_buy(self):
        assert format_signal_emoji("BUY") == "🟢"

    def test_hold(self):
        assert format_signal_emoji("HOLD") == "🟡"

    def test_watch(self):
        assert format_signal_emoji("WATCH") == "🔵"

    def test_reduce(self):
        assert format_signal_emoji("REDUCE") == "🔴"

    def test_unknown(self):
        assert format_signal_emoji("UNKNOWN") == "⚪"


# ---------------------------------------------------------------------------
# Tests for report generation
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_file_created(self, tmp_path):
        """Report file should be created with today's date."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)

        assert Path(filepath).exists()
        assert filepath.endswith(".md")
        assert "weekly_" in filepath

    def test_report_contains_header(self, tmp_path):
        """Report should have a header with date and summary stats."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "意怠投资周报" in content
        assert "跟踪公司数" in content
        assert "信号汇总" in content

    def test_report_contains_all_companies(self, tmp_path):
        """Report should have sections for each tracked company."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "腾讯控股" in content
        assert "0700.HK" in content
        assert "Apple Inc." in content
        assert "AAPL" in content
        assert "弱鸡科技" in content
        assert "WEAK.SZ" in content

    def test_report_contains_scores(self, tmp_path):
        """Report should contain dimension scores and visual bars."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        # Should have score bars
        assert "█" in content
        assert "░" in content

        # Should have dimension names
        assert "盈利能力" in content
        assert "财务健康" in content
        assert "现金流" in content
        assert "估值" in content
        assert "成长性" in content
        assert "股权结构" in content
        assert "战略" in content

    def test_report_contains_signals(self, tmp_path):
        """Report should contain signal emojis and Chinese labels."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "🟢" in content  # BUY emoji
        assert "买入" in content
        assert "🟡" in content  # HOLD emoji
        assert "持有" in content
        assert "🔴" in content  # REDUCE emoji
        assert "减仓" in content

    def test_report_contains_grades(self, tmp_path):
        """Report should show letter grades."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "评级" in content
        # We have A, B, and F grades in our test data
        assert "A" in content
        assert "B" in content

    def test_report_contains_portfolio_overview(self, tmp_path):
        """Report should have a portfolio overview section."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "组合概览" in content
        assert "评级分布" in content
        assert "信号分布" in content

    def test_report_contains_week_changes(self, tmp_path):
        """Report should show week-over-week changes for companies with history."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        # Tencent had a signal change from HOLD to BUY
        assert "本周变化" in content
        assert "信号变更" in content

    def test_report_contains_alerts(self, tmp_path):
        """Report should list signal-change alerts."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "重要提醒" in content
        # Tencent changed from HOLD to BUY
        assert "腾讯控股" in content

    def test_report_contains_disclaimer(self, tmp_path):
        """Report should end with a disclaimer."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "不构成投资建议" in content

    def test_report_empty_db(self, tmp_path):
        """Report generation should work even with an empty database."""
        db_path = str(tmp_path / "empty.duckdb")
        output_dir = str(tmp_path / "reports")
        YidaiStore(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert Path(filepath).exists()
        assert "意怠投资周报" in content
        assert "跟踪公司数" in content

    def test_report_contains_price_info(self, tmp_path):
        """Report should show price and valuation metrics."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "当前价格" in content
        assert "市盈率" in content

    def test_report_contains_sector_info(self, tmp_path):
        """Report should show sector information."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        _seed_store(db_path).close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "行业" in content
        assert "Technology" in content

    def test_report_no_score_company(self, tmp_path):
        """Company with no scores should still appear with a note."""
        db_path = str(tmp_path / "test.duckdb")
        output_dir = str(tmp_path / "reports")
        store = YidaiStore(db_path)
        store.upsert_company({
            "ticker": "NOSCORE.HK",
            "name": "无数据公司",
            "market": "HK",
            "currency": "HKD",
            "sector": "Unknown",
        })
        store.close()

        filepath = generate_report(db_path, output_dir)
        content = Path(filepath).read_text(encoding="utf-8")

        assert "无数据公司" in content
        assert "暂无评分数据" in content
