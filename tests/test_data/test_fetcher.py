"""Tests for eastmoney data fetcher."""

import unittest
from unittest.mock import patch, MagicMock

from src.data.fetcher import EastmoneyFetcher


def _mock_response(json_data, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m


# Sample A-share income response
A_INCOME = _mock_response({
    "result": {"data": [
        {
            "SECURITY_CODE": "002352",
            "REPORT_DATE": "2024-09-30 00:00:00",
            "TOTAL_OPERATE_INCOME": 50000000000.0,
            "MLR": 8000000000.0,
            "PARENT_NETPROFIT": 6000000000.0,
            "OPERATE_PROFIT": 7000000000.0,
            "EPSJB": 2.5,
            "TOTAL_SHARE": 3000000000.0,
        },
        {
            "SECURITY_CODE": "002352",
            "REPORT_DATE": "2024-06-30 00:00:00",
            "TOTAL_OPERATE_INCOME": 30000000000.0,
            "MLR": 5000000000.0,
            "PARENT_NETPROFIT": 3500000000.0,
            "OPERATE_PROFIT": 4200000000.0,
            "EPSJB": 1.5,
            "TOTAL_SHARE": 3000000000.0,
        },
    ]}
})

# Sample A-share balance response
A_BALANCE = _mock_response({
    "result": {"data": [
        {
            "SECURITY_CODE": "002352",
            "REPORT_DATE": "2024-09-30 00:00:00",
            "TOTAL_ASSETS": 200000000000.0,
            "TOTAL_LIABILITIES": 120000000000.0,
            "TOTAL_EQUITY": 80000000000.0,
            "TOTAL_CURRENT_ASSETS": 100000000000.0,
            "TOTAL_CURRENT_LIAB": 60000000000.0,
            "SHORT_LOAN": 20000000000.0,
            "LONG_LOAN": 30000000000.0,
            "BOND_PAYABLE": 5000000000.0,
        },
    ]}
})

# Sample A-share cashflow response
A_CASHFLOW = _mock_response({
    "result": {"data": [
        {
            "SECURITY_CODE": "002352",
            "REPORT_DATE": "2024-09-30 00:00:00",
            "NETCASH_OPERATE": 15000000000.0,
            "CONSTRUCT_LONG_ASSET": -5000000000.0,
        },
    ]}
})

# Sample HK main indicator response
HK_MAIN = _mock_response({
    "result": {"data": [
        {
            "SECUCODE": "01810.HK",
            "REPORT_DATE": "2024-09-30 00:00:00",
            "OPERATE_INCOME": 250000000000.0,
            "GROSS_PROFIT": 100000000000.0,
            "HOLDER_PROFIT": 50000000000.0,
            "OPERATE_PROFIT": 60000000000.0,
            "TOTAL_ASSETS": 500000000000.0,
            "TOTAL_LIABILITIES": None,
            "DEBT_ASSET_RATIO": 60.0,
            "TOTAL_PARENT_EQUITY": 200000000000.0,
            "NETCASH_OPERATE": 80000000000.0,
            "BASIC_EPS": 1.85,
        },
    ]}
})

# Sample price response
PRICE_RESP = _mock_response({
    "data": {
        "f43": 15230,  # 152.30 yuan or HK$
        "f116": 500000000000,
        "f162": 2500,   # PE 25.00
        "f167": 350,    # PB 3.50
    }
})


class TestHelpers(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    def test_safe_float_normal(self):
        self.assertEqual(self.f._safe_float(1234.5), 1234.5)
        self.assertEqual(self.f._safe_float("678.9"), 678.9)
        self.assertEqual(self.f._safe_float(0), 0.0)

    def test_safe_float_none_and_dash(self):
        self.assertIsNone(self.f._safe_float(None))
        self.assertIsNone(self.f._safe_float("-"))
        self.assertIsNone(self.f._safe_float("--"))
        self.assertIsNone(self.f._safe_float(""))

    def test_parse_date_datetime(self):
        self.assertEqual(self.f._parse_date("2024-09-30 00:00:00"), "2024-09-30")

    def test_parse_date_iso(self):
        self.assertEqual(self.f._parse_date("2024-09-30"), "2024-09-30")

    def test_parse_date_empty(self):
        self.assertEqual(self.f._parse_date(""), "")


class TestDetectMarket(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    def test_6digit_sz(self):
        m, c = self.f._detect_market("002352")
        self.assertEqual(m, "a_share")
        self.assertEqual(c, "002352")

    def test_6digit_sh(self):
        m, c = self.f._detect_market("601828")
        self.assertEqual(m, "a_share")
        self.assertEqual(c, "601828")

    def test_5digit_hk(self):
        m, c = self.f._detect_market("01810")
        self.assertEqual(m, "hk")
        self.assertEqual(c, "01810")

    def test_dot_hk(self):
        m, c = self.f._detect_market("01810.HK")
        self.assertEqual(m, "hk")
        self.assertEqual(c, "01810")

    def test_dot_sz(self):
        m, c = self.f._detect_market("002352.SZ")
        self.assertEqual(m, "a_share")
        self.assertEqual(c, "002352")


class TestFetchFinancialsAShare(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    @patch("src.data.fetcher.requests.get")
    def test_basic(self, mock_get):
        mock_get.side_effect = [A_INCOME, A_BALANCE, A_CASHFLOW]
        results = self.f.fetch_financials_a_share("002352", periods=2)
        self.assertEqual(len(results), 2)
        # Check first period
        d = results[0]
        self.assertEqual(d["ticker"], "002352")
        self.assertEqual(d["period"], "2024-09-30")
        self.assertEqual(d["report_date"], "2024-09-30")
        self.assertAlmostEqual(d["revenue"], 50000000000.0)
        self.assertAlmostEqual(d["gross_profit"], 8000000000.0)
        self.assertAlmostEqual(d["net_income"], 6000000000.0)
        self.assertAlmostEqual(d["operating_income"], 7000000000.0)
        self.assertAlmostEqual(d["total_assets"], 200000000000.0)
        self.assertAlmostEqual(d["total_liabilities"], 120000000000.0)
        self.assertAlmostEqual(d["total_equity"], 80000000000.0)
        self.assertAlmostEqual(d["interest_bearing_debt"], 55000000000.0)
        self.assertAlmostEqual(d["operating_cash_flow"], 15000000000.0)
        self.assertAlmostEqual(d["capex"], -5000000000.0)
        self.assertAlmostEqual(d["free_cash_flow"], 10000000000.0)
        self.assertAlmostEqual(d["eps"], 2.5)
        self.assertAlmostEqual(d["shares_outstanding"], 3000000000.0)

    def test_field_names(self):
        """Returned dicts should have all FinancialStatement field names."""
        with patch("src.data.fetcher.requests.get", side_effect=[A_INCOME, A_BALANCE, A_CASHFLOW]):
            results = self.f.fetch_financials_a_share("002352", periods=1)
        from src.data.fetcher import FINANCIAL_FIELDS
        for field in FINANCIAL_FIELDS:
            self.assertIn(field, results[0], f"Missing field: {field}")


class TestFetchFinancialsHK(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    @patch("src.data.fetcher.requests.get")
    def test_basic(self, mock_get):
        mock_get.return_value = HK_MAIN
        results = self.f.fetch_financials_hk("01810", periods=1)
        self.assertEqual(len(results), 1)
        d = results[0]
        self.assertEqual(d["ticker"], "01810")
        self.assertEqual(d["period"], "2024-09-30")
        # HK data divided by 1000
        self.assertAlmostEqual(d["revenue"], 250000000000.0)
        self.assertAlmostEqual(d["gross_profit"], 100000000000.0)
        self.assertAlmostEqual(d["net_income"], 50000000000.0)
        # total_liabilities derived from ratio: 1000000000000 * 60/100 = 600000000000
        self.assertAlmostEqual(d["total_liabilities"], 300000000000.0)
        self.assertAlmostEqual(d["total_equity"], 200000000000.0)
        self.assertAlmostEqual(d["operating_cash_flow"], 80000000000.0)
        self.assertAlmostEqual(d["eps"], 1.85)  # EPS not divided


class TestFetchPriceAShare(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    @patch("src.data.fetcher.requests.get")
    def test_basic(self, mock_get):
        mock_get.return_value = PRICE_RESP
        d = self.f.fetch_price_a_share("002352")
        self.assertEqual(d["ticker"], "002352")
        self.assertAlmostEqual(d["close_price"], 152.30)
        self.assertAlmostEqual(d["pe_ratio"], 25.0)
        self.assertAlmostEqual(d["pb_ratio"], 3.5)
        self.assertEqual(d["market_cap"], 500000000000)

    def test_field_names(self):
        with patch("src.data.fetcher.requests.get", return_value=PRICE_RESP):
            d = self.f.fetch_price_a_share("002352")
        from src.data.fetcher import PRICE_FIELDS
        for field in PRICE_FIELDS:
            self.assertIn(field, d, f"Missing field: {field}")


class TestFetchPriceHK(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    @patch("src.data.fetcher.requests.get")
    def test_basic(self, mock_get):
        # HK price now uses MAININDICATOR endpoint
        hk_price_mock = _mock_response({
            "result": {"data": [{
                "REPORT_DATE": "2025-12-31 00:00:00",
                "PE_TTM": 16.7,
                "PB_TTM": 2.53,
                "TOTAL_MARKET_CAP": 770000000000.0,
                "ISSUED_COMMON_SHARES": 25800000000.0,
                "BASIC_EPS": 1.62,
            }]}
        })
        mock_get.return_value = hk_price_mock
        d = self.f.fetch_price_hk("01810")
        self.assertEqual(d["ticker"], "01810")
        self.assertAlmostEqual(d["close_price"], 770000000000.0 / 25800000000.0)
        self.assertAlmostEqual(d["pe_ratio"], 16.7)
        self.assertAlmostEqual(d["pb_ratio"], 2.53)
        self.assertAlmostEqual(d["market_cap"], 770000000000.0)


class TestAutoDetect(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    @patch("src.data.fetcher.requests.get", return_value=PRICE_RESP)
    def test_fetch_price_a(self, mock_get):
        self.f.fetch_price("002352")
        call_url = mock_get.call_args
        self.assertIn("0.002352", str(call_url))

    @patch("src.data.fetcher.requests.get", return_value=PRICE_RESP)
    def test_fetch_price_sh(self, mock_get):
        self.f.fetch_price("601828")
        call_url = mock_get.call_args
        self.assertIn("1.601828", str(call_url))

    @patch("src.data.fetcher.requests.get")
    def test_fetch_price_hk(self, mock_get):
        hk_mock = _mock_response({
            "result": {"data": [{
                "PE_TTM": 19.0, "PB_TTM": 2.5,
                "TOTAL_MARKET_CAP": 770000000000.0,
                "ISSUED_COMMON_SHARES": 25800000000.0,
                "BASIC_EPS": 1.62,
            }]}
        })
        mock_get.return_value = hk_mock
        d = self.f.fetch_price("01810")
        self.assertEqual(d["ticker"], "01810")
        # Should call MAININDICATOR endpoint
        call_url = str(mock_get.call_args)
        self.assertIn("RPT_HKF10_FN_MAININDICATOR", call_url)

    @patch("src.data.fetcher.requests.get", return_value=HK_MAIN)
    def test_fetch_financials_hk_ticker(self, mock_get):
        results = self.f.fetch_financials("01810.HK", periods=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticker"], "01810")


class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        self.f = EastmoneyFetcher()

    @patch("src.data.fetcher.requests.get")
    def test_network_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.ConnectionError("fail")
        results = self.f.fetch_financials_a_share("002352", periods=1)
        self.assertEqual(results, [])

    @patch("src.data.fetcher.requests.get")
    def test_empty_response(self, mock_get):
        mock_get.return_value = _mock_response({"result": {"data": []}})
        results = self.f.fetch_financials_hk("01810", periods=1)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
