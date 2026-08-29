"""Tests for YiDAI data models."""

from datetime import date
from src.data.models import (
    Company,
    FinancialStatement,
    PriceData,
    QualitativeAssessment,
    ScoreResult,
)


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class TestCompany:
    def test_company_creation_all_fields(self):
        c = Company(
            ticker="0700.HK",
            name="Tencent Holdings",
            market="HK",
            currency="HKD",
            sector="Technology",
            notes="Large-cap tech",
        )
        assert c.ticker == "0700.HK"
        assert c.name == "Tencent Holdings"
        assert c.market == "HK"
        assert c.currency == "HKD"
        assert c.sector == "Technology"
        assert c.notes == "Large-cap tech"

    def test_company_default_notes(self):
        c = Company(
            ticker="AAPL",
            name="Apple Inc.",
            market="US",
            currency="USD",
            sector="Technology",
        )
        assert c.notes == ""


# ---------------------------------------------------------------------------
# FinancialStatement
# ---------------------------------------------------------------------------

class TestFinancialStatement:
    def test_financial_statement_creation_all_fields(self):
        fs = FinancialStatement(
            ticker="0700.HK",
            period="FY2024",
            report_date=date(2024, 12, 31),
            revenue=609_015_000_000,
            gross_profit=307_000_000_000,
            net_income=157_749_000_000,
            operating_income=180_000_000_000,
            total_assets=1_654_000_000_000,
            total_liabilities=762_000_000_000,
            total_equity=892_000_000_000,
            current_assets=580_000_000_000,
            current_liabilities=400_000_000_000,
            interest_bearing_debt=250_000_000_000,
            operating_cash_flow=220_000_000_000,
            capex=-50_000_000_000,
            free_cash_flow=170_000_000_000,
            shares_outstanding=9_500_000_000,
            eps=16.6,
        )
        assert fs.ticker == "0700.HK"
        assert fs.period == "FY2024"
        assert fs.report_date == date(2024, 12, 31)
        assert fs.revenue == 609_015_000_000
        assert fs.gross_profit == 307_000_000_000
        assert fs.net_income == 157_749_000_000
        assert fs.operating_income == 180_000_000_000
        assert fs.total_assets == 1_654_000_000_000
        assert fs.total_liabilities == 762_000_000_000
        assert fs.total_equity == 892_000_000_000
        assert fs.current_assets == 580_000_000_000
        assert fs.current_liabilities == 400_000_000_000
        assert fs.interest_bearing_debt == 250_000_000_000
        assert fs.operating_cash_flow == 220_000_000_000
        assert fs.capex == -50_000_000_000
        assert fs.free_cash_flow == 170_000_000_000
        assert fs.shares_outstanding == 9_500_000_000
        assert fs.eps == 16.6

    def test_financial_statement_defaults_none(self):
        fs = FinancialStatement(
            ticker="TEST",
            period="FY2023",
            report_date=date(2023, 12, 31),
        )
        assert fs.revenue is None
        assert fs.eps is None
        assert fs.free_cash_flow is None


# ---------------------------------------------------------------------------
# PriceData
# ---------------------------------------------------------------------------

class TestPriceData:
    def test_price_data_creation(self):
        p = PriceData(
            ticker="0700.HK",
            date=date(2024, 12, 31),
            close_price=380.0,
            market_cap=3_600_000_000_000,
            pe_ratio=22.0,
            pb_ratio=4.0,
            ps_ratio=6.0,
        )
        assert p.ticker == "0700.HK"
        assert p.close_price == 380.0
        assert p.pe_ratio == 22.0


# ---------------------------------------------------------------------------
# QualitativeAssessment
# ---------------------------------------------------------------------------

class TestQualitativeAssessment:
    def test_qualitative_assessment_creation(self):
        qa = QualitativeAssessment(
            ticker="0700.HK",
            date=date(2024, 12, 31),
            dimension="ownership",
            checklist={"founder-led": "yes", "insider-selling": "no"},
            score=4,
            notes="Strong founder involvement",
        )
        assert qa.ticker == "0700.HK"
        assert qa.dimension == "ownership"
        assert qa.score == 4
        assert qa.checklist["founder-led"] == "yes"


# ---------------------------------------------------------------------------
# ScoreResult  —  auto-computed total_score, grade, signal
# ---------------------------------------------------------------------------

class TestScoreResultAutoComputation:
    """Verify __post_init__ correctly computes total, grade, and signal."""

    def test_all_fives(self):
        """All 5s => total=35, grade='A', signal='BUY'."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=5,
            health_score=5,
            cashflow_score=5,
            valuation_score=5,
            growth_score=5,
            ownership_score=5,
            strategy_score=5,
        )
        assert sr.total_score == 35
        assert sr.grade == "A"
        assert sr.signal == "BUY"

    def test_all_threes(self):
        """All 3s => total=21, grade='C', signal='HOLD'."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=3,
            health_score=3,
            cashflow_score=3,
            valuation_score=3,
            growth_score=3,
            ownership_score=3,
            strategy_score=3,
        )
        assert sr.total_score == 21
        assert sr.grade == "C"
        assert sr.signal == "HOLD"

    def test_health_score_one_triggers_reduce(self):
        """health_score=1 (一票否决) => signal='REDUCE' even if others high."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=5,
            health_score=1,
            cashflow_score=5,
            valuation_score=5,
            growth_score=5,
            ownership_score=5,
            strategy_score=5,
        )
        assert sr.total_score == 31
        assert sr.grade == "A"
        assert sr.signal == "REDUCE"

    def test_cashflow_score_one_triggers_reduce(self):
        """cashflow_score=1 => signal='REDUCE'."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=5,
            health_score=5,
            cashflow_score=1,
            valuation_score=5,
            growth_score=5,
            ownership_score=5,
            strategy_score=5,
        )
        assert sr.signal == "REDUCE"

    def test_ownership_score_zero_blocks_buy(self):
        """ownership_score=0 => qualitative_confirmed=False => HOLD not BUY."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=5,
            health_score=5,
            cashflow_score=5,
            valuation_score=5,
            growth_score=5,
            ownership_score=0,
            strategy_score=5,
        )
        # ownership=0 blocks BUY but doesn't trigger REDUCE
        assert sr.signal in ("HOLD", "WATCH")
        assert sr.signal != "BUY"

    def test_all_ones(self):
        """All 1s => total=7, grade='F', signal='REDUCE'."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=1,
            health_score=1,
            cashflow_score=1,
            valuation_score=1,
            growth_score=1,
            ownership_score=1,
            strategy_score=1,
        )
        assert sr.total_score == 7
        assert sr.grade == "F"
        assert sr.signal == "REDUCE"

    def test_all_zeros(self):
        """All 0s => total=0, grade='F', signal='REDUCE'."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
        )
        assert sr.total_score == 0
        assert sr.grade == "F"
        assert sr.signal == "REDUCE"

    def test_grade_boundary_b(self):
        """total=22 should be grade='B'."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=3,
            health_score=3,
            cashflow_score=3,
            valuation_score=3,
            growth_score=3,
            ownership_score=4,
            strategy_score=3,
        )
        assert sr.total_score == 22
        assert sr.grade == "B"

    def test_grade_boundary_d(self):
        """total=14 with all >= 2 => grade='D', signal='REDUCE' (total <= 14)."""
        sr = ScoreResult(
            ticker="TEST",
            date=date(2024, 1, 1),
            profitability_score=2,
            health_score=2,
            cashflow_score=2,
            valuation_score=2,
            growth_score=2,
            ownership_score=2,
            strategy_score=2,
        )
        assert sr.total_score == 14
        assert sr.grade == "D"
        assert sr.signal == "REDUCE"
