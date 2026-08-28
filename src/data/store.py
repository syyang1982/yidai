"""
DuckDB storage layer for YiDAI investment research system.

Provides persistent storage for company info, financial statements,
price data, qualitative assessments, and 7-dimension score results.
"""

import duckdb
from pathlib import Path
from typing import Optional


class YidaiStore:
    """DuckDB-backed store for investment research data."""

    def __init__(self, db_path: str = "yidai.duckdb"):
        """Initialize store and create tables if they don't exist."""
        self.db_path = db_path
        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        """Create all tables if they do not already exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS company (
                ticker VARCHAR PRIMARY KEY,
                name VARCHAR,
                market VARCHAR,
                currency VARCHAR,
                sector VARCHAR,
                notes VARCHAR
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS financial_statement (
                ticker VARCHAR,
                period VARCHAR,
                report_date DATE,
                revenue DOUBLE,
                gross_profit DOUBLE,
                net_income DOUBLE,
                operating_income DOUBLE,
                ebitda DOUBLE,
                total_assets DOUBLE,
                total_liabilities DOUBLE,
                total_equity DOUBLE,
                current_assets DOUBLE,
                current_liabilities DOUBLE,
                interest_bearing_debt DOUBLE,
                operating_cash_flow DOUBLE,
                capex DOUBLE,
                free_cash_flow DOUBLE,
                shares_outstanding DOUBLE,
                eps DOUBLE,
                PRIMARY KEY (ticker, period)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS price_data (
                ticker VARCHAR,
                date DATE,
                close_price DOUBLE,
                market_cap DOUBLE,
                pe_ratio DOUBLE,
                pb_ratio DOUBLE,
                ps_ratio DOUBLE,
                PRIMARY KEY (ticker, date)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS qualitative_assessment (
                ticker VARCHAR,
                date DATE,
                dimension VARCHAR,
                checklist JSON,
                score INTEGER,
                notes VARCHAR,
                PRIMARY KEY (ticker, date, dimension)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS score_result (
                ticker VARCHAR,
                date DATE,
                profitability_score INTEGER,
                health_score INTEGER,
                cashflow_score INTEGER,
                valuation_score INTEGER,
                growth_score INTEGER,
                ownership_score INTEGER,
                strategy_score INTEGER,
                total_score INTEGER,
                grade VARCHAR,
                signal VARCHAR,
                PRIMARY KEY (ticker, date)
            )
        """)

        # Migration: add ebitda column if table already exists without it
        try:
            self.conn.execute(
                "ALTER TABLE financial_statement ADD COLUMN IF NOT EXISTS ebitda DOUBLE"
            )
        except Exception:
            pass  # table may not exist yet, that's fine

    def upsert_company(self, company_data: dict):
        """Insert or update a company record."""
        self.conn.execute("""
            INSERT INTO company (ticker, name, market, currency, sector, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker) DO UPDATE SET
                name = EXCLUDED.name,
                market = EXCLUDED.market,
                currency = EXCLUDED.currency,
                sector = EXCLUDED.sector,
                notes = EXCLUDED.notes
        """, [
            company_data.get("ticker"),
            company_data.get("name"),
            company_data.get("market"),
            company_data.get("currency"),
            company_data.get("sector"),
            company_data.get("notes"),
        ])

    def upsert_financial(self, statement: dict):
        """Insert or update a financial statement record."""
        self.conn.execute("""
            INSERT INTO financial_statement (
                ticker, period, report_date, revenue, gross_profit, net_income,
                operating_income, ebitda, total_assets, total_liabilities, total_equity,
                current_assets, current_liabilities, interest_bearing_debt,
                operating_cash_flow, capex, free_cash_flow, shares_outstanding, eps
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, period) DO UPDATE SET
                report_date = EXCLUDED.report_date,
                revenue = EXCLUDED.revenue,
                gross_profit = EXCLUDED.gross_profit,
                net_income = EXCLUDED.net_income,
                operating_income = EXCLUDED.operating_income,
                ebitda = EXCLUDED.ebitda,
                total_assets = EXCLUDED.total_assets,
                total_liabilities = EXCLUDED.total_liabilities,
                total_equity = EXCLUDED.total_equity,
                current_assets = EXCLUDED.current_assets,
                current_liabilities = EXCLUDED.current_liabilities,
                interest_bearing_debt = EXCLUDED.interest_bearing_debt,
                operating_cash_flow = EXCLUDED.operating_cash_flow,
                capex = EXCLUDED.capex,
                free_cash_flow = EXCLUDED.free_cash_flow,
                shares_outstanding = EXCLUDED.shares_outstanding,
                eps = EXCLUDED.eps
        """, [
            statement.get("ticker"),
            statement.get("period"),
            statement.get("report_date"),
            statement.get("revenue"),
            statement.get("gross_profit"),
            statement.get("net_income"),
            statement.get("operating_income"),
            statement.get("ebitda"),
            statement.get("total_assets"),
            statement.get("total_liabilities"),
            statement.get("total_equity"),
            statement.get("current_assets"),
            statement.get("current_liabilities"),
            statement.get("interest_bearing_debt"),
            statement.get("operating_cash_flow"),
            statement.get("capex"),
            statement.get("free_cash_flow"),
            statement.get("shares_outstanding"),
            statement.get("eps"),
        ])

    def upsert_price(self, price: dict):
        """Insert or update a price data record."""
        self.conn.execute("""
            INSERT INTO price_data (ticker, date, close_price, market_cap, pe_ratio, pb_ratio, ps_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, date) DO UPDATE SET
                close_price = EXCLUDED.close_price,
                market_cap = EXCLUDED.market_cap,
                pe_ratio = EXCLUDED.pe_ratio,
                pb_ratio = EXCLUDED.pb_ratio,
                ps_ratio = EXCLUDED.ps_ratio
        """, [
            price.get("ticker"),
            price.get("date"),
            price.get("close_price"),
            price.get("market_cap"),
            price.get("pe_ratio"),
            price.get("pb_ratio"),
            price.get("ps_ratio"),
        ])

    def upsert_qualitative(self, assessment: dict):
        """Insert or update a qualitative assessment record."""
        self.conn.execute("""
            INSERT INTO qualitative_assessment (ticker, date, dimension, checklist, score, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, date, dimension) DO UPDATE SET
                checklist = EXCLUDED.checklist,
                score = EXCLUDED.score,
                notes = EXCLUDED.notes
        """, [
            assessment.get("ticker"),
            assessment.get("date"),
            assessment.get("dimension"),
            assessment.get("checklist"),
            assessment.get("score"),
            assessment.get("notes"),
        ])

    def upsert_score(self, score: dict):
        """Insert or update a score result record."""
        self.conn.execute("""
            INSERT INTO score_result (
                ticker, date, profitability_score, health_score, cashflow_score,
                valuation_score, growth_score, ownership_score, strategy_score,
                total_score, grade, signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, date) DO UPDATE SET
                profitability_score = EXCLUDED.profitability_score,
                health_score = EXCLUDED.health_score,
                cashflow_score = EXCLUDED.cashflow_score,
                valuation_score = EXCLUDED.valuation_score,
                growth_score = EXCLUDED.growth_score,
                ownership_score = EXCLUDED.ownership_score,
                strategy_score = EXCLUDED.strategy_score,
                total_score = EXCLUDED.total_score,
                grade = EXCLUDED.grade,
                signal = EXCLUDED.signal
        """, [
            score.get("ticker"),
            score.get("date"),
            score.get("profitability_score"),
            score.get("health_score"),
            score.get("cashflow_score"),
            score.get("valuation_score"),
            score.get("growth_score"),
            score.get("ownership_score"),
            score.get("strategy_score"),
            score.get("total_score"),
            score.get("grade"),
            score.get("signal"),
        ])

    def get_financials(self, ticker: str, period: Optional[str] = None) -> list:
        """
        Retrieve financial statements for a ticker.

        If period is specified, return that single period.
        Otherwise return all periods sorted by period (ascending).
        """
        if period is not None:
            result = self.conn.execute(
                "SELECT * FROM financial_statement WHERE ticker = ? AND period = ?",
                [ticker, period]
            ).fetchall()
        else:
            result = self.conn.execute(
                "SELECT * FROM financial_statement WHERE ticker = ? ORDER BY period",
                [ticker]
            ).fetchall()

        columns = [
            "ticker", "period", "report_date", "revenue", "gross_profit",
            "net_income", "operating_income", "ebitda", "total_assets", "total_liabilities",
            "total_equity", "current_assets", "current_liabilities",
            "interest_bearing_debt", "operating_cash_flow", "capex",
            "free_cash_flow", "shares_outstanding", "eps",
        ]
        return [dict(zip(columns, row)) for row in result]

    def get_latest_price(self, ticker: str) -> Optional[dict]:
        """Retrieve the most recent price data for a ticker, or None if no data."""
        result = self.conn.execute(
            "SELECT * FROM price_data WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            [ticker]
        ).fetchone()

        if result is None:
            return None

        columns = ["ticker", "date", "close_price", "market_cap", "pe_ratio", "pb_ratio", "ps_ratio"]
        return dict(zip(columns, result))

    def get_scores(self, ticker: str) -> list:
        """Retrieve all score results for a ticker, sorted by date ascending."""
        result = self.conn.execute(
            "SELECT * FROM score_result WHERE ticker = ? ORDER BY date",
            [ticker]
        ).fetchall()

        columns = [
            "ticker", "date", "profitability_score", "health_score",
            "cashflow_score", "valuation_score", "growth_score",
            "ownership_score", "strategy_score", "total_score",
            "grade", "signal",
        ]
        return [dict(zip(columns, row)) for row in result]

    def get_all_tickers(self) -> list:
        """Return a list of all tickers in the company table."""
        result = self.conn.execute("SELECT ticker FROM company ORDER BY ticker").fetchall()
        return [row[0] for row in result]

    def close(self):
        """Close the database connection."""
        self.conn.close()
