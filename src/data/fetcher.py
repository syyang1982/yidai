"""Eastmoney data fetcher for A-share and HK stocks."""

import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Common field names for FinancialStatement and PriceData dicts
FINANCIAL_FIELDS = [
    "ticker", "period", "report_date", "revenue", "gross_profit", "net_income",
    "operating_income", "ebitda", "total_assets", "total_liabilities", "total_equity",
    "current_assets", "current_liabilities", "interest_bearing_debt",
    "operating_cash_flow", "capex", "free_cash_flow", "shares_outstanding", "eps",
]

PRICE_FIELDS = ["ticker", "date", "close_price", "market_cap", "pe_ratio", "pb_ratio", "ps_ratio"]


class EastmoneyFetcher:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    TIMEOUT = 30

    # ---- helpers ----

    def _safe_float(self, val) -> Optional[float]:
        if val is None or val in ("-", "--", "", "None"):
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _parse_date(self, date_str: str) -> str:
        if not date_str:
            return ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(date_str[:len(fmt.replace('%', ' ').strip())], fmt).strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                continue
        # fallback: take first 10 chars if looks like date
        if len(date_str) >= 10 and date_str[4] in ("-", "/") and date_str[7] in ("-", "/"):
            return date_str[:10].replace("/", "-")
        return date_str

    def _detect_market(self, ticker: str) -> tuple[str, str]:
        """Return (market, code). market is 'a_share' or 'hk'."""
        t = ticker.strip().upper()
        if t.endswith(".HK"):
            return "hk", t.replace(".HK", "")
        if t.endswith(".SZ"):
            return "a_share", t.replace(".SZ", "")
        if t.endswith(".SH"):
            return "a_share", t.replace(".SH", "")
        # bare digits
        code = t
        if len(t) in (4, 5):
            return "hk", t
        if len(t) == 6:
            return "a_share", t
        # US stock tickers: 1-5 uppercase letters
        if t.isalpha() and 1 <= len(t) <= 5:
            return "us", t
        raise ValueError(f"Cannot detect market for ticker: {ticker}")

    # ---- A-share financials ----

    def fetch_financials_a_share(self, code: str, periods: int = 5) -> list[dict]:
        """Fetch A-share financial statements from eastmoney datacenter API."""
        base_url = "https://datacenter.eastmoney.com/securities/api/data/get"
        report_types = {
            "RPT_F10_FINANCE_GINCOME": "income",
            "RPT_F10_FINANCE_GBALANCE": "balance",
            "RPT_F10_FINANCE_GCASHFLOW": "cashflow",
        }
        all_data: dict[str, dict] = {}  # period_key -> merged dict

        for rpt_type, label in report_types.items():
            params = {
                "type": rpt_type,
                "sty": "ALL",
                "filter": f'(SECURITY_CODE="{code}")',
                "p": 1,
                "ps": periods,
                "sr": -1,
                "st": "REPORT_DATE",
            }
            try:
                resp = requests.get(base_url, params=params, headers=self.HEADERS, timeout=self.TIMEOUT)
                resp.raise_for_status()
                body = resp.json()
                rows = (body.get("result") or {}).get("data") or []
            except (requests.RequestException, ValueError, KeyError) as e:
                logger.warning("Failed to fetch A-share %s for %s: %s", label, code, e)
                rows = []

            for row in rows:
                period = self._parse_date(row.get("REPORT_DATE", ""))
                if period not in all_data:
                    all_data[period] = {"period": period, "report_date": period}
                d = all_data[period]

                if label == "income":
                    d["revenue"] = self._safe_float(row.get("TOTAL_OPERATE_INCOME") or row.get("TOTALOPERATEREVE"))
                    d["gross_profit"] = self._safe_float(row.get("MLR") or row.get("OPERATE_PROFIT"))
                    d["net_income"] = self._safe_float(row.get("PARENT_NETPROFIT"))
                    d["operating_income"] = self._safe_float(row.get("OPERATE_PROFIT"))
                    d["ebitda"] = self._safe_float(row.get("EBITDA"))
                    d["eps"] = self._safe_float(row.get("EPSJB"))
                    d["shares_outstanding"] = self._safe_float(row.get("TOTAL_SHARE"))
                elif label == "balance":
                    d["total_assets"] = self._safe_float(row.get("TOTAL_ASSETS"))
                    d["total_liabilities"] = self._safe_float(row.get("TOTAL_LIABILITIES"))
                    d["total_equity"] = self._safe_float(row.get("TOTAL_EQUITY"))
                    d["current_assets"] = self._safe_float(row.get("TOTAL_CURRENT_ASSETS"))
                    d["current_liabilities"] = self._safe_float(row.get("TOTAL_CURRENT_LIAB"))
                    short_loan = self._safe_float(row.get("SHORT_LOAN")) or 0
                    long_loan = self._safe_float(row.get("LONG_LOAN")) or 0
                    bond = self._safe_float(row.get("BOND_PAYABLE")) or 0
                    d["interest_bearing_debt"] = short_loan + long_loan + bond if (short_loan + long_loan + bond) else None
                    # Extra fields for anomaly detection (optional, backward-compatible)
                    d["accounts_receivable"] = self._safe_float(row.get("ACCOUNTS_RECE"))
                    d["inventory"] = self._safe_float(row.get("INVENTORY"))
                    d["goodwill"] = self._safe_float(row.get("GOODWILL"))
                    d["short_loan"] = self._safe_float(row.get("SHORT_LOAN"))
                    d["long_loan"] = self._safe_float(row.get("LONG_LOAN"))
                    d["long_term_invest"] = self._safe_float(row.get("LONG_TERM_INVEST"))
                elif label == "cashflow":
                    d["operating_cash_flow"] = self._safe_float(row.get("NETCASH_OPERATE"))
                    cpx = self._safe_float(row.get("CONSTRUCT_LONG_ASSET"))
                    d["capex"] = cpx
                    ocf = d.get("operating_cash_flow") or 0
                    if cpx is not None and ocf:
                        d["free_cash_flow"] = ocf + cpx  # capex is negative

        results = []
        for period_key in sorted(all_data.keys(), reverse=True)[:periods]:
            d = all_data[period_key]
            d["ticker"] = code
            results.append(d)
        return results

    # ---- HK financials ----

    def fetch_financials_hk(self, code: str, periods: int = 5) -> list[dict]:
        """Fetch HK stock financial statements."""
        secucode = f"{code.zfill(5)}.HK"
        base_url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"

        # Main indicators
        params = {
            "reportName": "RPT_HKF10_FN_MAININDICATOR",
            "columns": "ALL",
            "filter": f'(SECUCODE="{secucode}")',
            "source": "F10",
            "client": "PC",
            "p": 1,
            "ps": max(periods * 4, 40),  # fetch extra to ensure we get enough annual reports
            "sr": -1,
            "st": "REPORT_DATE",
        }
        try:
            resp = requests.get(base_url, params=params, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            rows = (body.get("result") or {}).get("data") or []
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Failed to fetch HK main indicator for %s: %s", code, e)
            rows = []

        # Sort by REPORT_DATE descending to ensure latest first
        rows.sort(key=lambda r: r.get("REPORT_DATE", ""), reverse=True)

        results = []
        for row in rows:
            period = self._parse_date(row.get("REPORT_DATE", ""))
            revenue = self._safe_float(row.get("OPERATE_INCOME"))
            gp = self._safe_float(row.get("GROSS_PROFIT"))
            ni = self._safe_float(row.get("HOLDER_PROFIT"))
            total_assets = self._safe_float(row.get("TOTAL_ASSETS"))
            total_liab = self._safe_float(row.get("TOTAL_LIABILITIES"))
            # Derive total_liabilities from ratio if missing
            if total_liab is None and total_assets is not None:
                ratio = self._safe_float(row.get("DEBT_ASSET_RATIO"))
                if ratio is not None:
                    total_liab = total_assets * ratio / 100.0
            equity = self._safe_float(row.get("TOTAL_PARENT_EQUITY"))
            ocf = self._safe_float(row.get("NETCASH_OPERATE"))
            eps = self._safe_float(row.get("BASIC_EPS"))

            d = {
                "ticker": code,
                "period": period,
                "report_date": period,
                "revenue": revenue,
                "gross_profit": gp,
                "net_income": ni,
                "operating_income": self._safe_float(row.get("OPERATE_PROFIT")),
                "ebitda": self._safe_float(row.get("EBITDA")),
                "total_assets": total_assets,
                "total_liabilities": total_liab,
                "total_equity": equity,
                "current_assets": self._safe_float(row.get("CURRENT_RATIO")),  # placeholder
                "current_liabilities": None,
                "interest_bearing_debt": None,
                "operating_cash_flow": ocf,
                "capex": None,
                "free_cash_flow": None,
                "shares_outstanding": None,
                "eps": eps,  # EPS is per-share, not in thousands
                "dividend_per_share": self._safe_float(row.get("DPS_HKD")),
            }

            # Calculate free cash flow if possible
            if d["operating_cash_flow"] is not None and d["capex"] is not None:
                d["free_cash_flow"] = d["operating_cash_flow"] + d["capex"]

            results.append(d)

        return results

    # ---- A-share price ----

    def fetch_price_a_share(self, code: str) -> dict:
        """Fetch real-time A-share price."""
        prefix = "1" if code.startswith("6") else "0"
        secid = f"{prefix}.{code}"
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f116,f117,f162,f167",
        }
        headers = {**self.HEADERS, "Referer": "https://quote.eastmoney.com/"}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", {})
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Failed to fetch A-share price for %s: %s", code, e)
            data = {}

        price_fen = self._safe_float(data.get("f43"))
        pe_raw = self._safe_float(data.get("f162"))
        pb_raw = self._safe_float(data.get("f167"))
        return {
            "ticker": code,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "close_price": price_fen / 100.0 if price_fen is not None else None,
            "market_cap": self._safe_float(data.get("f116")),
            "pe_ratio": pe_raw / 100.0 if pe_raw is not None else None,
            "pb_ratio": pb_raw / 100.0 if pb_raw is not None else None,
            "ps_ratio": None,
        }

    # ---- HK price ----

    def fetch_price_hk(self, code: str) -> dict:
        """Fetch HK stock price from MAININDICATOR (has PE_TTM, PB_TTM, TOTAL_MARKET_CAP).
        Falls back to push2.eastmoney.com if available."""
        # Try MAININDICATOR first (always works for financial data)
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "reportName": "RPT_HKF10_FN_MAININDICATOR",
            "columns": "REPORT_DATE,PE_TTM,PB_TTM,TOTAL_MARKET_CAP,OPERATE_INCOME,ISSUED_COMMON_SHARES,BASIC_EPS",
            "filter": f'(SECUCODE="{code}.HK")',
            "pageNumber": 1, "pageSize": 1,
            "sortTypes": "-1", "sortColumns": "REPORT_DATE",
            "source": "F10", "client": "PC",
        }
        data = {}
        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            rows = (body.get("result") or {}).get("data") or []
            if rows:
                data = rows[0]
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Failed to fetch HK indicator for %s: %s", code, e)

        pe = self._safe_float(data.get("PE_TTM"))
        pb = self._safe_float(data.get("PB_TTM"))
        mkt_cap = self._safe_float(data.get("TOTAL_MARKET_CAP"))
        shares = self._safe_float(data.get("ISSUED_COMMON_SHARES"))
        eps = self._safe_float(data.get("BASIC_EPS"))

        # Derive price from PE * EPS or market_cap / shares
        price = None
        if False and pe and eps:  # disabled, use market_cap/shares
            price = pe * eps
        elif mkt_cap and shares and shares > 0:
            price = mkt_cap / shares

        return {
            "ticker": code,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "close_price": price,
            "market_cap": mkt_cap,
            "pe_ratio": pe,
            "pb_ratio": pb,
            "ps_ratio": None,
        }

    # ---- US price ----

    def fetch_price_us(self, code: str) -> dict:
        """Fetch US stock price from eastmoney push2 API."""
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {"secid": f"105.{code}", "fields": "f43,f57,f58,f116,f117,f162,f167"}
        headers = {**self.HEADERS, "Referer": "https://quote.eastmoney.com/"}
        data = {}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", {})
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Failed to fetch US price for %s: %s", code, e)

        price_cents = self._safe_float(data.get("f43"))
        return {
            "ticker": code,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "close_price": price_cents / 100.0 if price_cents else None,
            "market_cap": self._safe_float(data.get("f116")),
            "pe_ratio": None,  # US PE not available from this endpoint
            "pb_ratio": self._safe_float(data.get("f167")),
            "ps_ratio": None,
        }

    # ---- Peer data for valuation comparison ----

    # Industry peer groups for PE comparison
    PEER_GROUPS = {
        # Battery / 动力电池
        "battery": [
            ("300750", "a_share"),  # 宁德时代
            ("300014", "a_share"),  # 亿纬锂能
            ("002074", "a_share"),  # 国轩高科
            ("688567", "a_share"),  # 孚能科技
            ("03931", "hk"),       # 中创新航
        ],
        # Auto parts / 汽车零部件
        "auto_parts": [
            ("601689", "a_share"),  # 拓普集团
            ("002050", "a_share"),  # 三花智控
            ("600933", "a_share"),  # 爱柯迪
        ],
        # Laser / 激光雷达
        "lidar": [
            ("02525", "hk"),       # 禾赛科技
            ("02498", "hk"),       # 速腾聚创
        ],
        # Robot components / 机器人零部件
        "robot_parts": [
            ("688017", "a_share"),  # 绿的谐波
            ("301528", "a_share"),  # 来福谐波
        ],
        # Internet / 互联网
        "internet": [
            ("01810", "hk"),       # 小米
            ("09988", "hk"),       # 阿里
            ("09999", "hk"),       # 网易
        ],
        # Tea drinks / 茶饮
        "tea_drinks": [
            ("02097", "hk"),       # 蜜雪集团
            # CHA (霸王茶姬) is US-listed, no eastmoney data
        ],
    }

    # Reverse lookup: ticker_code -> peer_group name
    _TICKER_TO_PEER_GROUP: dict[str, str] = {}

    @classmethod
    def _build_ticker_to_group(cls):
        if cls._TICKER_TO_PEER_GROUP:
            return
        for group, members in cls.PEER_GROUPS.items():
            for code, _market in members:
                cls._TICKER_TO_PEER_GROUP[code] = group

    def fetch_peer_pe(self, ticker: str) -> dict | None:
        """Fetch PE ratios for peer companies in the same industry.

        Returns dict with 'peer_median_pe', 'peer_pes' (list of (name, pe)),
        or None if ticker not in any peer group.
        """
        self._build_ticker_to_group()
        market, code = self._detect_market(ticker)
        group_name = self._TICKER_TO_PEER_GROUP.get(code)
        if not group_name:
            return None

        peers = self.PEER_GROUPS[group_name]
        peer_pes = []
        for peer_code, peer_market in peers:
            if peer_code == code:
                continue  # skip self
            try:
                if peer_market == "hk":
                    p = self.fetch_price_hk(peer_code)
                else:
                    p = self.fetch_price_a_share(peer_code)
                pe = p.get("pe_ratio")
                if pe is not None and pe > 0:
                    peer_pes.append((peer_code, pe))
            except Exception:
                pass

        if not peer_pes:
            return None

        # Compute median
        sorted_pes = sorted([pe for _, pe in peer_pes])
        n = len(sorted_pes)
        if n % 2 == 1:
            median_pe = sorted_pes[n // 2]
        else:
            median_pe = (sorted_pes[n // 2 - 1] + sorted_pes[n // 2]) / 2

        return {
            "peer_median_pe": median_pe,
            "peer_pes": peer_pes,
            "peer_group": group_name,
        }

    # ---- Insider activity (reductions + issuances) ----

    def fetch_insider_activity_a_share(self, code: str, lookback_days: int = 365) -> list[dict]:
        """Fetch A-share insider trading and share issuance events.

        Sources:
          - RPT_CUSTOM_SHARE_HOLD_CHANGE: shareholder/top-holders changes
          - RPT_OR_ISSUEPLAN: share issuance plans (定增/配股/可转债)

        Returns list of event dicts compatible with insider_activity.check_insider_activity().
        """
        from datetime import timedelta
        events: list[dict] = []
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        # --- 1. Shareholder/insider reductions ---
        url = "https://datacenter.eastmoney.com/securities/api/data/get"
        params = {
            "type": "RPT_CUSTOM_SHARE_HOLD_CHANGE",
            "sty": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "p": 1,
            "ps": 50,
            "sr": -1,
            "st": "CHANGE_DATE",
        }
        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            rows = (body.get("result") or {}).get("data") or []
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.debug("Failed to fetch insider reductions for %s: %s", code, e)
            rows = []

        for row in rows:
            change_date = self._parse_date(row.get("CHANGE_DATE", ""))
            if not change_date or change_date < cutoff:
                continue

            holder_name = row.get("HOLDER_NAME", "")
            holder_type_raw = row.get("HOLDER_TYPE", "")
            # Classify holder type
            if any(kw in holder_type_raw for kw in ("控股股东", "实际控制人", "第一大股东")):
                holder_type = "major"
            elif any(kw in holder_type_raw for kw in ("董事", "高管", "监事", "总经理", "副总")):
                holder_type = "executive"
            else:
                holder_type = holder_type_raw or "institutional"

            change_shares = self._safe_float(row.get("CHANGE_SHARES"))
            change_pct = self._safe_float(row.get("HOLD_SHARES_RATIO_CHANGE"))
            avg_price = self._safe_float(row.get("AVERAGE_PRICE"))
            change_after = self._safe_float(row.get("CHANGE_AFTER_SHARES"))

            # Negative change_shares = selling
            if change_shares is not None and change_shares < 0:
                amount = abs(change_shares) * (avg_price or 0)
                events.append({
                    "event_type": "reduction",
                    "date": change_date,
                    "holder_type": holder_type,
                    "holder_name": holder_name,
                    "shares_traded": change_shares,
                    "shares_pct": abs(change_pct) if change_pct else None,
                    "amount": amount,
                    "price": avg_price,
                    "holding_after": change_after,
                })

        # --- 2. Share issuance plans ---
        params2 = {
            "type": "RPT_OR_ISSUEPLAN",
            "sty": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "p": 1,
            "ps": 20,
            "sr": -1,
            "st": "ISSUE_DATE",
        }
        try:
            resp2 = requests.get(url, params=params2, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp2.raise_for_status()
            body2 = resp2.json()
            rows2 = (body2.get("result") or {}).get("data") or []
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.debug("Failed to fetch issuance plans for %s: %s", code, e)
            rows2 = []

        for row in rows2:
            issue_date = self._parse_date(row.get("ISSUE_DATE", "") or row.get("PLAN_DATE", ""))
            if not issue_date or issue_date < cutoff:
                continue

            issue_type = row.get("ISSUE_TYPE", "")
            issue_amount = self._safe_float(row.get("ISSUE_AMOUNT"))
            issue_shares = self._safe_float(row.get("ISSUE_NUM"))
            issue_price = self._safe_float(row.get("ISSUE_PRICE"))

            # Map issue type to Chinese label
            type_map = {
                "1": "定增", "定向增发": "定增", "非公开发行": "定增",
                "2": "配股", "配股": "配股",
                "3": "公开增发", "公开增发": "公开增发",
                "4": "可转债", "可转债": "可转债",
            }
            issuance_type = type_map.get(str(issue_type), issue_type or "增发")

            # Only record active/completed issuances (status filtering)
            status = row.get("ISSUE_STATUS", "")
            # Skip cancelled/failed
            if any(kw in str(status) for kw in ("终止", "撤回", "失败", "取消")):
                continue

            events.append({
                "event_type": "issuance",
                "date": issue_date,
                "issuance_type": issuance_type,
                "amount": issue_amount,
                "shares": issue_shares,
                "price": issue_price,
                "status": status,
                "holder_name": f"上市公司{issuance_type}",
            })

        return events

    def fetch_insider_activity_hk(self, code: str, lookback_days: int = 365) -> list[dict]:
        """Fetch HK stock insider trading events.

        Uses the HK disclosure of interests API.
        Returns list of event dicts compatible with insider_activity.check_insider_activity().
        """
        from datetime import timedelta
        events: list[dict] = []
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        secucode = f"{code.zfill(5)}.HK"

        # HK disclosure of interests (权益披露)
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "reportName": "RPT_HKF10_FN_DISCLOSURE",
            "columns": "ALL",
            "filter": f'(SECUCODE="{secucode}")',
            "source": "F10",
            "client": "PC",
            "p": 1,
            "ps": 50,
            "sr": -1,
            "st": "CHANGE_DATE",
        }
        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            rows = (body.get("result") or {}).get("data") or []
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.debug("Failed to fetch HK insider data for %s: %s", code, e)
            rows = []

        for row in rows:
            change_date = self._parse_date(row.get("CHANGE_DATE", ""))
            if not change_date or change_date < cutoff:
                continue

            holder_name = row.get("HOLDER_NAME", "") or row.get("LNAME", "")
            shares_after = self._safe_float(row.get("SHARES_AFTER"))
            shares_before = self._safe_float(row.get("SHARES_BEFORE"))
            pct_after = self._safe_float(row.get("PCT_AFTER"))
            pct_before = self._safe_float(row.get("PCT_BEFORE"))

            # Determine if this is a reduction
            if shares_before and shares_after and shares_after < shares_before:
                change_shares = shares_after - shares_before
                change_pct = abs((pct_before or 0) - (pct_after or 0))

                # Classify holder type based on role
                role = row.get("POSITION", "") or row.get("ROLE", "")
                if any(kw in str(role) for kw in ("控股股东", "实控", "Controlling")):
                    holder_type = "major"
                elif any(kw in str(role) for kw in ("董事", "高管", "Director", "Officer")):
                    holder_type = "executive"
                else:
                    holder_type = "institutional"

                events.append({
                    "event_type": "reduction",
                    "date": change_date,
                    "holder_type": holder_type,
                    "holder_name": holder_name,
                    "shares_traded": change_shares,
                    "shares_pct": change_pct if change_pct > 0 else None,
                    "amount": None,  # HK disclosure doesn't always include amount
                    "price": None,
                    "holding_after": shares_after,
                })

        return events

    def fetch_insider_activity(self, ticker: str, lookback_days: int = 365) -> list[dict]:
        """Auto-detect market and fetch insider activity events.

        Returns list of event dicts for check_insider_activity().
        """
        market, code = self._detect_market(ticker)
        if market == "hk":
            return self.fetch_insider_activity_hk(code, lookback_days)
        if market == "us":
            return []  # US insider data not available from eastmoney
        return self.fetch_insider_activity_a_share(code, lookback_days)

    # ---- Top shareholders (for ownership structure analysis) ----

    def fetch_top_shareholders_a_share(self, code: str) -> list[dict]:
        """Fetch A-share top 10 shareholders (十大股东).

        Uses RPT_F10_EH_HOLDERSLIST endpoint.

        Returns list of dicts with:
            - name: shareholder name
            - pct: holding percentage (e.g. 15.3 for 15.3%)
            - shares: number of shares held
            - type: 'natural_person' / 'legal_entity' / 'state' / etc.
            - change: change direction ('increase'/'decrease'/'unchanged')
        """
        url = "https://datacenter.eastmoney.com/securities/api/data/get"
        params = {
            "type": "RPT_F10_EH_HOLDERSLIST",
            "sty": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "p": 1,
            "ps": 10,
            "sr": -1,
            "st": "END_DATE",
        }
        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            rows = (body.get("result") or {}).get("data") or []
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.debug("Failed to fetch top shareholders for %s: %s", code, e)
            rows = []

        if not rows:
            return []

        # Use the latest report date's shareholders
        # All rows from the same report period share END_DATE
        latest_date = rows[0].get("END_DATE", "")
        shareholders = []
        for row in rows:
            if row.get("END_DATE", "") != latest_date:
                break  # Only take the latest period

            name = row.get("HOLDER_NAME", "") or row.get("SNAME", "")
            pct = self._safe_float(row.get("HOLD_RATIO") or row.get("HOLDNUM_RATIO"))
            shares = self._safe_float(row.get("HOLD_NUM") or row.get("HOLDNUM"))
            holder_type_raw = row.get("HOLDER_TYPE", "") or ""

            # Classify type
            if any(kw in holder_type_raw for kw in ("国有", "国资", "State", "state")):
                holder_type = "state"
            elif any(kw in holder_type_raw for kw in ("基金", "Fund", "ETF", "QFII")):
                holder_type = "fund"
            elif any(kw in holder_type_raw for kw in ("公司", "集团", "有限", "Corp", "Ltd")):
                holder_type = "legal_entity"
            elif holder_type_raw:
                holder_type = "natural_person"
            else:
                # Infer from name patterns
                if any(kw in name for kw in ("有限", "集团", "公司", "Corp", "Ltd", "Inc")):
                    holder_type = "legal_entity"
                elif any(kw in name for kw in ("基金", "Fund", "ETF", "Asset")):
                    holder_type = "fund"
                else:
                    holder_type = "unknown"

            change_raw = row.get("HOLD_CHANGE", "") or ""
            if "增" in str(change_raw) or "+" in str(change_raw):
                change = "increase"
            elif "减" in str(change_raw) or "-" in str(change_raw):
                change = "decrease"
            else:
                change = "unchanged"

            shareholders.append({
                "name": name,
                "pct": pct or 0,
                "shares": shares,
                "type": holder_type,
                "change": change,
            })

        return shareholders

    def fetch_top_shareholders_hk(self, code: str) -> list[dict]:
        """Fetch HK stock top shareholders.

        Uses RPT_HKF10_FN_EHOLDERS or similar HK endpoint.

        Returns list of dicts compatible with ownership_structure.analyze_controller_status().
        """
        secucode = f"{code.zfill(5)}.HK"
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "reportName": "RPT_HKF10_FN_EHOLDERS",
            "columns": "ALL",
            "filter": f'(SECUCODE="{secucode}")',
            "source": "F10",
            "client": "PC",
            "p": 1,
            "ps": 10,
            "sr": -1,
            "st": "END_DATE",
        }
        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            rows = (body.get("result") or {}).get("data") or []
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.debug("Failed to fetch HK top shareholders for %s: %s", code, e)
            rows = []

        if not rows:
            return []

        # Use latest period only
        latest_date = rows[0].get("END_DATE", "")
        shareholders = []
        for row in rows:
            if row.get("END_DATE", "") != latest_date:
                break

            name = row.get("HOLDER_NAME", "") or row.get("LNAME", "")
            pct = self._safe_float(row.get("HOLD_RATIO") or row.get("RATIO"))
            shares = self._safe_float(row.get("HOLD_NUM") or row.get("SHARES"))

            # HK doesn't always provide holder type, infer from name
            holder_type = "unknown"
            if any(kw in name for kw in ("有限", "集团", "公司", "Corp", "Ltd",
                                          "Group", "Holdings", "Investment")):
                holder_type = "legal_entity"
            elif any(kw in name for kw in ("基金", "Fund", "ETF", "Asset", "Capital")):
                holder_type = "fund"
            elif name and not any(kw in name for kw in ("有限", "集团", "公司")):
                holder_type = "natural_person"

            shareholders.append({
                "name": name,
                "pct": pct or 0,
                "shares": shares,
                "type": holder_type,
                "change": "unknown",
            })

        return shareholders

    def fetch_top_shareholders(self, ticker: str) -> list[dict]:
        """Auto-detect market and fetch top shareholders.

        Returns list of shareholder dicts for ownership_structure.analyze_controller_status().
        """
        market, code = self._detect_market(ticker)
        if market == "hk":
            return self.fetch_top_shareholders_hk(code)
        if market == "us":
            return []
        return self.fetch_top_shareholders_a_share(code)

    # ---- Auto-detect wrappers ----

    def fetch_financials(self, ticker: str, periods: int = 5) -> list[dict]:
        market, code = self._detect_market(ticker)
        if market == "hk":
            return self.fetch_financials_hk(code, periods)
        if market == "us":
            return []  # US financials not supported yet
        return self.fetch_financials_a_share(code, periods)

    def fetch_price(self, ticker: str) -> dict:
        market, code = self._detect_market(ticker)
        if market == "hk":
            return self.fetch_price_hk(code)
        if market == "us":
            return self.fetch_price_us(code)
        return self.fetch_price_a_share(code)
