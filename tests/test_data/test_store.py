"""Tests for YiDAI DuckDB store layer."""

from datetime import date
from src.data.store import YidaiStore


def _make_store(tmp_path) -> YidaiStore:
    """Create a store backed by a temp DuckDB file."""
    return YidaiStore(str(tmp_path / "test.duckdb"))


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

class TestTableCreation:
    def test_tables_created_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_all_tickers() == []
        store.close()


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------

class TestCompanyStore:
    def test_upsert_company_and_get_all_tickers(self, tmp_path):
        store = _make_store(tmp_path)

        store.upsert_company({
            "ticker": "0700.HK",
            "name": "Tencent Holdings",
            "market": "HK",
            "currency": "HKD",
            "sector": "Technology",
            "notes": "",
        })
        store.upsert_company({
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "US",
            "currency": "USD",
            "sector": "Technology",
            "notes": "",
        })

        tickers = store.get_all_tickers()
        assert tickers == ["0700.HK", "AAPL"]  # sorted by ticker
        store.close()

    def test_upsert_company_update_existing(self, tmp_path):
        """ON CONFLICT should update existing record."""
        store = _make_store(tmp_path)

        store.upsert_company({
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "US",
            "currency": "USD",
            "sector": "Technology",
            "notes": "",
        })
        store.upsert_company({
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "US",
            "currency": "USD",
            "sector": "Consumer Electronics",
            "notes": "updated sector",
        })

        tickers = store.get_all_tickers()
        assert tickers == ["AAPL"]

        # Verify the update took effect
        rows = store.conn.execute(
            "SELECT sector, notes FROM company WHERE ticker = 'AAPL'"
        ).fetchone()
        assert rows[0] == "Consumer Electronics"
        assert rows[1] == "updated sector"
        store.close()


# ---------------------------------------------------------------------------
# Financial statements
# ---------------------------------------------------------------------------

class TestFinancialStore:
    def test_upsert_financial_and_get_single_period(self, tmp_path):
        store = _make_store(tmp_path)

        store.upsert_financial({
            "ticker": "0700.HK",
            "period": "FY2024",
            "report_date": date(2024, 12, 31),
            "revenue": 609_015_000_000,
            "gross_profit": 307_000_000_000,
            "net_income": 157_749_000_000,
            "operating_income": 180_000_000_000,
            "total_assets": 1_654_000_000_000,
            "total_liabilities": 762_000_000_000,
            "total_equity": 892_000_000_000,
            "current_assets": 580_000_000_000,
            "current_liabilities": 400_000_000_000,
            "interest_bearing_debt": 250_000_000_000,
            "operating_cash_flow": 220_000_000_000,
            "capex": -50_000_000_000,
            "free_cash_flow": 170_000_000_000,
            "shares_outstanding": 9_500_000_000,
            "eps": 16.6,
        })

        result = store.get_financials("0700.HK", period="FY2024")
        assert len(result) == 1
        assert result[0]["ticker"] == "0700.HK"
        assert result[0]["period"] == "FY2024"
        assert result[0]["revenue"] == 609_015_000_000
        assert result[0]["eps"] == 16.6
        store.close()

    def test_get_financials_multi_period_sorted(self, tmp_path):
        store = _make_store(tmp_path)

        # Insert out of order
        for period, rev in [("FY2023", 100.0), ("FY2024", 200.0), ("FY2022", 50.0)]:
            store.upsert_financial({
                "ticker": "TEST",
                "period": period,
                "report_date": date(2024, 1, 1),
                "revenue": rev,
            })

        result = store.get_financials("TEST")
        assert len(result) == 3
        # Should be sorted ascending by period
        assert [r["period"] for r in result] == ["FY2022", "FY2023", "FY2024"]
        store.close()

    def test_upsert_financial_update_existing(self, tmp_path):
        store = _make_store(tmp_path)

        store.upsert_financial({
            "ticker": "TEST",
            "period": "FY2024",
            "report_date": date(2024, 1, 1),
            "revenue": 100.0,
            "eps": 1.0,
        })
        store.upsert_financial({
            "ticker": "TEST",
            "period": "FY2024",
            "report_date": date(2024, 12, 31),
            "revenue": 200.0,
            "eps": 2.0,
        })

        result = store.get_financials("TEST", period="FY2024")
        assert len(result) == 1
        assert result[0]["revenue"] == 200.0
        assert result[0]["eps"] == 2.0
        assert result[0]["report_date"] == date(2024, 12, 31)
        store.close()


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

class TestPriceStore:
    def test_upsert_price_and_get_latest(self, tmp_path):
        store = _make_store(tmp_path)

        store.upsert_price({
            "ticker": "0700.HK",
            "date": date(2024, 12, 30),
            "close_price": 370.0,
            "market_cap": 3_500_000_000_000,
            "pe_ratio": 21.0,
            "pb_ratio": 3.8,
            "ps_ratio": 5.5,
        })
        store.upsert_price({
            "ticker": "0700.HK",
            "date": date(2024, 12, 31),
            "close_price": 380.0,
            "market_cap": 3_600_000_000_000,
            "pe_ratio": 22.0,
            "pb_ratio": 4.0,
            "ps_ratio": 6.0,
        })

        latest = store.get_latest_price("0700.HK")
        assert latest is not None
        assert latest["ticker"] == "0700.HK"
        assert latest["date"] == date(2024, 12, 31)
        assert latest["close_price"] == 380.0
        store.close()

    def test_get_latest_price_none_when_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_latest_price("NOPE") is None
        store.close()

    def test_upsert_price_update_existing(self, tmp_path):
        store = _make_store(tmp_path)

        store.upsert_price({
            "ticker": "TEST",
            "date": date(2024, 1, 1),
            "close_price": 100.0,
        })
        store.upsert_price({
            "ticker": "TEST",
            "date": date(2024, 1, 1),
            "close_price": 150.0,
        })

        latest = store.get_latest_price("TEST")
        assert latest["close_price"] == 150.0
        store.close()


# ---------------------------------------------------------------------------
# Score results
# ---------------------------------------------------------------------------

class TestScoreStore:
    def test_upsert_score_and_get_scores(self, tmp_path):
        store = _make_store(tmp_path)

        store.upsert_score({
            "ticker": "TEST",
            "date": date(2024, 1, 1),
            "profitability_score": 5,
            "health_score": 5,
            "cashflow_score": 5,
            "valuation_score": 5,
            "growth_score": 5,
            "ownership_score": 5,
            "strategy_score": 5,
            "total_score": 35,
            "grade": "A",
            "signal": "BUY",
        })

        scores = store.get_scores("TEST")
        assert len(scores) == 1
        assert scores[0]["ticker"] == "TEST"
        assert scores[0]["total_score"] == 35
        assert scores[0]["grade"] == "A"
        assert scores[0]["signal"] == "BUY"
        store.close()

    def test_get_scores_sorted_by_date(self, tmp_path):
        store = _make_store(tmp_path)

        for d, total in [(date(2024, 6, 1), 20), (date(2024, 1, 1), 10)]:
            store.upsert_score({
                "ticker": "TEST",
                "date": d,
                "profitability_score": 3,
                "health_score": 3,
                "cashflow_score": 3,
                "valuation_score": 3,
                "growth_score": 3,
                "ownership_score": 3,
                "strategy_score": 2,
                "total_score": total,
                "grade": "C",
                "signal": "HOLD",
            })

        scores = store.get_scores("TEST")
        assert len(scores) == 2
        assert scores[0]["date"] == date(2024, 1, 1)
        assert scores[1]["date"] == date(2024, 6, 1)
        store.close()

    def test_upsert_score_update_existing(self, tmp_path):
        store = _make_store(tmp_path)

        store.upsert_score({
            "ticker": "TEST",
            "date": date(2024, 1, 1),
            "profitability_score": 3,
            "health_score": 3,
            "cashflow_score": 3,
            "valuation_score": 3,
            "growth_score": 3,
            "ownership_score": 3,
            "strategy_score": 3,
            "total_score": 21,
            "grade": "C",
            "signal": "HOLD",
        })
        store.upsert_score({
            "ticker": "TEST",
            "date": date(2024, 1, 1),
            "profitability_score": 5,
            "health_score": 5,
            "cashflow_score": 5,
            "valuation_score": 5,
            "growth_score": 5,
            "ownership_score": 5,
            "strategy_score": 5,
            "total_score": 35,
            "grade": "A",
            "signal": "BUY",
        })

        scores = store.get_scores("TEST")
        assert len(scores) == 1
        assert scores[0]["total_score"] == 35
        assert scores[0]["signal"] == "BUY"
        store.close()


# ---------------------------------------------------------------------------
# Cross-entity integration
# ---------------------------------------------------------------------------

class TestStoreIntegration:
    def test_multiple_tickers_isolated(self, tmp_path):
        """Verify data for different tickers doesn't leak."""
        store = _make_store(tmp_path)

        store.upsert_company({
            "ticker": "A",
            "name": "Alpha",
            "market": "US",
            "currency": "USD",
            "sector": "Tech",
        })
        store.upsert_company({
            "ticker": "B",
            "name": "Beta",
            "market": "US",
            "currency": "USD",
            "sector": "Finance",
        })
        store.upsert_financial({
            "ticker": "A",
            "period": "FY2024",
            "report_date": date(2024, 12, 31),
            "revenue": 100.0,
        })
        store.upsert_price({
            "ticker": "B",
            "date": date(2024, 12, 31),
            "close_price": 50.0,
        })

        assert store.get_financials("A") != []
        assert store.get_financials("B") == []
        assert store.get_latest_price("A") is None
        assert store.get_latest_price("B") is not None
        store.close()
