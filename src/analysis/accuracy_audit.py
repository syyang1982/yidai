"""Signal accuracy audit module.

Audits historical signal accuracy by comparing signal prices
to current prices and checking directional correctness.
Supports multi-window accuracy calculation via Yahoo Finance historical prices.
"""

from __future__ import annotations

import json
import time as _time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import requests


DEFAULT_DB_PATH = Path.home() / ".hermes" / "yidai" / "db" / "signals.duckdb"


class AccuracyAuditor:
    """Audits signal accuracy against current prices."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        # Ensure time_window_prices column exists
        self._ensure_time_window_column()

    def _ensure_time_window_column(self) -> None:
        """Add time_window_prices column if it doesn't exist."""
        try:
            conn = duckdb.connect(self.db_path)
            conn.execute(
                "ALTER TABLE signal_records ADD COLUMN IF NOT EXISTS "
                "time_window_prices JSON"
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # Table may not exist yet, or column already present

    def _calculate_return_pct(
        self, signal_price: float, current_price: float
    ) -> Optional[float]:
        """Calculate return percentage: (current - signal) / signal.

        Returns None if signal_price is zero to avoid division by zero.
        """
        if signal_price == 0:
            return None
        return (current_price - signal_price) / signal_price

    def _is_direction_correct(
        self, signal_type: str, signal_price: float, current_price: float
    ) -> bool:
        """Check if the price movement matches the signal's expected direction.

        BUY:    correct when return > 0
        REDUCE: correct when return < 0
        HOLD:   correct when |return| < 10%
        WATCH:  always False (no directional expectation)
        """
        ret = self._calculate_return_pct(signal_price, current_price)
        if ret is None:
            return False

        if signal_type == "BUY":
            return ret > 0
        elif signal_type == "REDUCE":
            return ret < 0
        elif signal_type == "HOLD":
            return abs(ret) < 0.10
        else:  # WATCH or unknown
            return False

    # ------------------------------------------------------------------
    # Yahoo Finance helpers
    # ------------------------------------------------------------------

    def _to_yahoo_ticker(self, ticker: str) -> Optional[str]:
        """Convert internal ticker format to Yahoo Finance format.

        Rules:
        - 01810.HK -> 1810.HK (strip leading zeros for HK)
        - 9988.HK  -> 9988.HK (no change)
        - 600519.SS -> 600519.SS (A-share Shanghai, no change)
        - 300750.SZ -> 300750.SZ (A-share Shenzhen, no change)
        - 600900.SH -> 600900.SS (SH -> SS for Yahoo)
        - LX       -> LX (US stock, no change)
        - 09698    -> 9698.HK (5-digit numeric -> HK)
        - 300602   -> 300602.SZ (6-digit, starts with 3 -> SZ)
        - 601689   -> 601689.SS (6-digit, starts with 6 -> SS)
        - 002415   -> 002415.SZ (6-digit, starts with 0/3 -> SZ)
        """
        t = ticker.strip().upper()

        # Already has market suffix
        if t.endswith(".HK"):
            code = t.replace(".HK", "").lstrip("0") or "0"
            return f"{code}.HK"
        if t.endswith(".SS"):
            return t
        if t.endswith(".SZ"):
            return t
        if t.endswith(".SH"):
            return t.replace(".SH", ".SS")

        # Pure numeric
        if t.isdigit():
            if len(t) == 5:  # HK stocks
                code = t.lstrip("0") or "0"
                return f"{code}.HK"
            if len(t) == 6:
                if t.startswith("6"):
                    return f"{t}.SS"
                else:
                    return f"{t}.SZ"

        # US stocks (pure alpha)
        if t.isalpha():
            return t

        return None

    def fetch_price_at_date(
        self, ticker: str, target_date: str
    ) -> Optional[float]:
        """Fetch the closing price of *ticker* on *target_date* via Yahoo Finance v8 chart API.

        Args:
            ticker: Internal ticker format (e.g. 01810.HK, 600519.SS, LX).
            target_date: ISO date string YYYY-MM-DD.

        Returns:
            The closing price closest to *target_date*, or None on failure.
        """
        yahoo_ticker = self._to_yahoo_ticker(ticker)
        if not yahoo_ticker:
            return None

        try:
            target = datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            return None

        start_ts = str(int((target - timedelta(days=7)).timestamp()))
        end_ts = str(int((target + timedelta(days=7)).timestamp()))

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
        params = {
            "period1": start_ts,
            "period2": end_ts,
            "interval": "1d",
        }
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None

        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        timestamps = result[0].get("timestamp", [])
        quote = result[0].get("indicators", {}).get("quote", [{}])
        closes = quote[0].get("close", []) if quote else []

        if not timestamps or not closes:
            return None

        # Find the price closest to target_date
        target_ts = target.timestamp()
        best_diff = float("inf")
        best_close = None
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            diff = abs(ts - target_ts)
            if diff < best_diff:
                best_diff = diff
                best_close = close

        return best_close

    # ------------------------------------------------------------------
    # Database queries
    # ------------------------------------------------------------------

    def load_pending_signals(self, min_days_old: int = 0) -> list[dict]:
        """Load signal records from DuckDB and parse JSON columns.

        Args:
            min_days_old: Only include signals whose signal_date is at
                least this many days in the past.  0 means no filter.

        Returns:
            List of dicts with parsed fields including signal_price
            (from company_state JSON), expected_price_6m (from
            prediction_6m JSON), dimension_scores (from JSON),
            actual_6m (from JSON), time_window_prices (from JSON).
        """
        conn = duckdb.connect(self.db_path, read_only=True)
        try:
            where_clause = ""
            params: list = []
            if min_days_old > 0:
                where_clause = (
                    f" WHERE signal_date <= CURRENT_DATE - INTERVAL '{min_days_old}' DAY"
                )

            sql = f"SELECT * FROM signal_records{where_clause} ORDER BY signal_date"
            result = conn.execute(sql, params).fetchall()
            col_names = [desc[0] for desc in conn.execute(
                f"SELECT * FROM signal_records{where_clause} LIMIT 0", params
            ).description]
        finally:
            conn.close()

        json_cols = {
            "company_state", "dimension_scores", "analysis_details",
            "prediction_6m", "prediction_12m", "actual_6m", "actual_12m",
            "prediction_accuracy", "time_window_prices",
        }

        records: list[dict] = []
        for row in result:
            rec = dict(zip(col_names, row))
            # Parse all JSON string columns
            for col in json_cols:
                val = rec.get(col)
                if val is not None and isinstance(val, str):
                    rec[col] = json.loads(val)

            # Extract convenience fields from nested JSON
            cs = rec.get("company_state") or {}
            rec["signal_price"] = cs.get("price") if cs else None

            p6 = rec.get("prediction_6m") or {}
            rec["expected_price_6m"] = p6.get("expected_price") if p6 else None

            records.append(rec)

        return records

    # ------------------------------------------------------------------
    # Statistical aggregation
    # ------------------------------------------------------------------

    def compute_accuracy_stats(
        self, records: list[dict], window_days: Optional[int] = None
    ) -> dict:
        """Compute direction accuracy and return statistics.

        Args:
            records: Each record must have ``signal_type``,
                ``signal_price``, and ``current_price`` (the actual
                observed price).  Optional: ``grade``,
                ``dimension_scores``, ``time_window_prices``.
            window_days: If specified (e.g. 90), use the price from
                ``time_window_prices[str(window_days)]`` as
                ``current_price`` instead of the record's own
                ``current_price``.  Records without that window are
                skipped.

        Returns:
            dict with keys: total, correct, direction_accuracy,
            avg_return_pct, by_type, by_grade, by_dimension.
        """
        total = 0
        correct = 0
        returns: list[float] = []

        by_type: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "correct": 0, "returns": []}
        )
        by_grade: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "correct": 0, "returns": []}
        )
        # by_dimension: {dim_name: {"high_correct": 0, "high_total": 0, ...}}
        dim_agg: dict[str, dict] = defaultdict(
            lambda: {
                "high_correct": 0, "high_total": 0,
                "low_correct": 0, "low_total": 0,
            }
        )

        for rec in records:
            signal_type = rec.get("signal_type", "")
            signal_price = rec.get("signal_price") or 0.0

            # Determine current_price: window-specific or latest
            if window_days is not None:
                twp = rec.get("time_window_prices", {})
                if isinstance(twp, str):
                    twp = json.loads(twp)
                wp = twp.get(str(window_days)) if isinstance(twp, dict) else None
                if wp and wp.get("price"):
                    current_price = wp["price"]
                else:
                    continue  # skip records without this window's price
            else:
                current_price = rec.get("current_price", 0.0)

            grade = rec.get("grade", "")
            dim_scores = rec.get("dimension_scores") or {}

            ret = self._calculate_return_pct(signal_price, current_price)
            is_correct = self._is_direction_correct(
                signal_type, signal_price, current_price
            )

            total += 1
            if is_correct:
                correct += 1
            if ret is not None:
                returns.append(ret)

            # --- by type ---
            bt = by_type[signal_type]
            bt["total"] += 1
            if is_correct:
                bt["correct"] += 1
            if ret is not None:
                bt["returns"].append(ret)

            # --- by grade ---
            bg = by_grade[grade]
            bg["total"] += 1
            if is_correct:
                bg["correct"] += 1
            if ret is not None:
                bg["returns"].append(ret)

            # --- by dimension ---
            for dim_name, score in dim_scores.items():
                da = dim_agg[dim_name]
                if score >= 3:
                    da["high_total"] += 1
                    if is_correct:
                        da["high_correct"] += 1
                else:
                    da["low_total"] += 1
                    if is_correct:
                        da["low_correct"] += 1

        # Finalize averages
        def _finalize(bucket: dict) -> dict:
            t = bucket["total"]
            c = bucket["correct"]
            rets = bucket["returns"]
            return {
                "total": t,
                "correct": c,
                "accuracy": c / t if t > 0 else 0.0,
                "avg_return": sum(rets) / len(rets) if rets else 0.0,
            }

        by_type_out = {k: _finalize(v) for k, v in by_type.items()}
        by_grade_out = {k: _finalize(v) for k, v in by_grade.items()}

        by_dimension_out: dict[str, dict] = {}
        for dim_name, da in dim_agg.items():
            ht = da["high_total"]
            hc = da["high_correct"]
            lt = da["low_total"]
            lc = da["low_correct"]
            high_acc = hc / ht if ht > 0 else 0.0
            low_acc = lc / lt if lt > 0 else 0.0
            by_dimension_out[dim_name] = {
                "high_score_accuracy": high_acc,
                "low_score_accuracy": low_acc,
                "high_count": ht,
                "low_count": lt,
                "predictive_power": high_acc - low_acc,
            }

        return {
            "total": total,
            "correct": correct,
            "direction_accuracy": correct / total if total > 0 else 0.0,
            "avg_return_pct": sum(returns) / len(returns) if returns else 0.0,
            "by_type": dict(by_type_out),
            "by_grade": dict(by_grade_out),
            "by_dimension": by_dimension_out,
        }

    # ------------------------------------------------------------------
    # Price backfill
    # ------------------------------------------------------------------

    def backfill_prices(
        self, fetcher=None, max_records: int = 100
    ) -> int:
        """Fetch current prices from eastmoney and write to actual_6m.

        Args:
            fetcher: An EastmoneyFetcher instance.  If None, one is created.
            max_records: Max number of records to process.

        Returns:
            Number of records successfully updated.
        """
        if fetcher is None:
            from src.data.fetcher import EastmoneyFetcher
            fetcher = EastmoneyFetcher()

        # 1. Read records with NULL actual_6m
        conn = duckdb.connect(self.db_path, read_only=True)
        try:
            result = conn.execute(
                "SELECT signal_id, ticker FROM signal_records "
                "WHERE actual_6m IS NULL LIMIT ?",
                [max_records],
            ).fetchall()
        finally:
            conn.close()

        if not result:
            return 0

        today = date.today().isoformat()
        updated = 0

        for signal_id, ticker in result:
            try:
                market, code = fetcher._detect_market(ticker)
                if market == "hk":
                    price_data = fetcher.fetch_price_hk(code)
                elif market == "a_share":
                    price_data = fetcher.fetch_price_a_share(code)
                elif market == "us":
                    price_data = fetcher.fetch_price_us(code)
                else:
                    continue

                close_price = price_data.get("close_price")
                actual_json = json.dumps({
                    "actual_price": close_price,
                    "backfill_date": today,
                })

                conn = duckdb.connect(self.db_path)
                try:
                    conn.execute(
                        "UPDATE signal_records SET actual_6m = ? WHERE signal_id = ?",
                        [actual_json, signal_id],
                    )
                finally:
                    conn.close()

                updated += 1
            except Exception:
                # Skip records that fail to fetch
                continue

        return updated

    def backfill_time_windows(
        self, window_days: Optional[list[int]] = None
    ) -> dict:
        """Backfill prices at fixed time windows after each signal date.

        For each signal record with a valid signal_price:
        1. Compute signal_date + N days for each window.
        2. Fetch closing price on that date via Yahoo Finance.
        3. Store in ``time_window_prices`` column.

        Args:
            window_days: List of window lengths in days.
                Defaults to [30, 60, 90, 180].

        Returns:
            Summary dict: total_signals, updated, skipped, by_window.
        """
        if window_days is None:
            window_days = [30, 60, 90, 180]

        conn = duckdb.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT signal_id, ticker, signal_date, signal_type, "
                "company_state, total_score, grade, dimension_scores "
                "FROM signal_records WHERE status != 'superseded' "
                "ORDER BY signal_date"
            ).fetchall()

            today = date.today()

            updated = 0
            skipped = 0
            by_window: dict[int, dict] = {
                w: {"fetched": 0, "too_recent": 0} for w in window_days
            }

            for row in rows:
                (
                    signal_id, ticker, signal_date, signal_type,
                    state_json, total_score, grade, dims_json,
                ) = row

                # Parse signal_price
                state = json.loads(state_json) if state_json else {}
                signal_price = state.get("price", 0) if isinstance(state, dict) else 0
                if not signal_price:
                    skipped += 1
                    continue

                # Parse signal_date
                if hasattr(signal_date, "strftime"):
                    sig_date = signal_date
                else:
                    sig_date = datetime.strptime(str(signal_date), "%Y-%m-%d").date()

                # Calculate price at each window
                window_prices: dict[str, dict] = {}
                for w in window_days:
                    target = sig_date + timedelta(days=w)
                    target_str = target.isoformat()

                    if target > today:
                        by_window[w]["too_recent"] += 1
                        continue

                    price = self.fetch_price_at_date(ticker, target_str)
                    if price is not None:
                        window_prices[str(w)] = {
                            "target_date": target_str,
                            "price": round(price, 4),
                        }
                        by_window[w]["fetched"] += 1

                    # Rate-limit: 0.3s between Yahoo API calls
                    _time.sleep(0.3)

                if window_prices:
                    conn.execute(
                        "UPDATE signal_records SET "
                        "time_window_prices = ?, "
                        "updated_at = CURRENT_TIMESTAMP "
                        "WHERE signal_id = ?",
                        [json.dumps(window_prices, ensure_ascii=False), signal_id],
                    )
                    updated += 1

            conn.commit()
            return {
                "total_signals": len(rows),
                "updated": updated,
                "skipped": skipped,
                "by_window": by_window,
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    def format_report(self, stats_or_result) -> str:
        """Format accuracy audit stats as a terminal report.

        Accepts either:
        - A flat stats dict (legacy, from compute_accuracy_stats) — uses
          the original single-section format.
        - A multi-window result dict (from generate_full_report) — renders
          one section per time window plus overall summary.

        Returns:
            Formatted string for terminal display.
        """
        # Detect multi-window result dict
        if "windows" in stats_or_result:
            return self._format_multi_window_report(stats_or_result)
        return self._format_legacy_report(stats_or_result)

    def _format_multi_window_report(self, result: dict) -> str:
        """Format multi-window report."""
        sep = "=" * 60
        thin = "─" * 56

        lines = [
            sep,
            "  📊 信号准确率审计报告 (固定时间窗口)",
            sep,
        ]

        # Per-window sections
        for w in sorted(result.get("windows", {}).keys()):
            stats = result["windows"][w]
            total = stats["total"]
            if total == 0:
                continue
            acc = stats["direction_accuracy"] * 100
            avg_ret = stats["avg_return_pct"] * 100

            icon = "🟢" if acc >= 60 else "🟡" if acc >= 50 else "🔴"
            lines.append(
                f"\n  {icon} {w}天窗口: 准确率 {acc:.1f}% "
                f"({stats['correct']}/{total}) 均收益{avg_ret:+.1f}%"
            )

            # by_type
            for sig_type in ["BUY", "HOLD", "REDUCE"]:
                bt = stats.get("by_type", {}).get(sig_type)
                if bt and bt["total"] > 0:
                    t_icon = (
                        "🟢" if bt["accuracy"] >= 0.6
                        else "🟡" if bt["accuracy"] >= 0.5
                        else "🔴"
                    )
                    lines.append(
                        f"    {t_icon} {sig_type}: "
                        f"{bt['accuracy']*100:.0f}% "
                        f"({bt['correct']}/{bt['total']}) "
                        f"{bt['avg_return']*100:+.1f}%"
                    )

        # Overall section
        overall = result.get("overall", {})
        if overall.get("total", 0) > 0:
            lines.append(f"\n  {thin}")
            lines.append(
                f"  📊 总体(最新价格): 准确率 "
                f"{overall['direction_accuracy']*100:.1f}% "
                f"({overall['correct']}/{overall['total']})"
            )

            # By type for overall
            by_type = overall.get("by_type", {})
            if by_type:
                lines.append(f"  {thin}")
                lines.append("  类型     样本   正确   准确率    平均收益")
                lines.append(f"  {thin}")
                for sig_type, bt in sorted(by_type.items()):
                    icon = {"BUY": "🟢", "REDUCE": "🔴", "HOLD": "🟡"}.get(sig_type, "⚪")
                    t = bt["total"]
                    c = bt["correct"]
                    a = bt["accuracy"] * 100
                    r = bt["avg_return"] * 100
                    lines.append(
                        f"  {icon} {sig_type:<7s} {t:>4d}   {c:>4d}   "
                        f"{a:>5.1f}%   {r:>+7.2f}%"
                    )

            # By grade for overall
            by_grade = overall.get("by_grade", {})
            if by_grade:
                lines += [
                    "",
                    f"  {thin}",
                    "  🎯 按评分等级 (A级信号是否更准?)",
                    f"  {thin}",
                    "  等级     样本   正确   准确率    平均收益",
                    f"  {thin}",
                ]
                for grade, bg in sorted(by_grade.items()):
                    icon = {"A": "🟢", "B": "🟡"}.get(grade, "🔴")
                    t = bg["total"]
                    c = bg["correct"]
                    a = bg["accuracy"] * 100
                    r = bg["avg_return"] * 100
                    lines.append(
                        f"  {icon} {grade:<7s} {t:>4d}   {c:>4d}   "
                        f"{a:>5.1f}%   {r:>+7.2f}%"
                    )

        # Dimension predictive power (from longest window)
        longest_w = max(result.get("windows", {}).keys(), default=0)
        if longest_w > 0:
            dims = result["windows"].get(longest_w, {}).get("by_dimension", {})
            if dims:
                lines.append(f"\n  {thin}")
                lines.append(f"  🔬 维度预测力 ({longest_w}天窗口)")
                lines.append(f"  {thin}")
                sorted_dims = sorted(
                    dims.items(),
                    key=lambda x: x[1].get("predictive_power", 0),
                    reverse=True,
                )
                for dim_name, dim_data in sorted_dims:
                    pp = dim_data.get("predictive_power", 0)
                    icon = "🟢" if pp > 0.1 else "🟡" if pp > 0 else "🔴"
                    lines.append(
                        f"    {icon} {dim_name:<8} 预测力={pp:+.2f} "
                        f"(高{dim_data.get('high_count',0)}条 "
                        f"{dim_data.get('high_score_accuracy',0):.0%} vs "
                        f"低{dim_data.get('low_count',0)}条 "
                        f"{dim_data.get('low_score_accuracy',0):.0%})"
                    )

        lines.append(f"\n{sep}")
        return "\n".join(lines)

    def _format_legacy_report(self, stats: dict) -> str:
        """Format a single flat stats dict (backward-compatible)."""
        sep = "=" * 60
        thin = "─" * 56

        total = stats["total"]
        correct = stats["correct"]
        acc = stats["direction_accuracy"] * 100
        avg_ret = stats["avg_return_pct"] * 100

        lines = [
            sep,
            "  📊 信号准确率审计报告",
            sep,
            "",
            f"  🟢 整体方向准确率: {acc:.1f}% ({correct}/{total})",
            f"  📈 平均收益率: {avg_ret:+.2f}%",
            f"  📊 样本量: {total} 条信号",
        ]

        # --- By type ---
        by_type = stats.get("by_type", {})
        if by_type:
            lines += [
                "",
                f"  {thin}",
                "  📋 按信号类型",
                f"  {thin}",
                "  类型     样本   正确   准确率    平均收益",
                f"  {thin}",
            ]
            for sig_type, bt in sorted(by_type.items()):
                icon = {"BUY": "🟢", "REDUCE": "🔴", "HOLD": "🟡"}.get(sig_type, "⚪")
                t = bt["total"]
                c = bt["correct"]
                a = bt["accuracy"] * 100
                r = bt["avg_return"] * 100
                lines.append(
                    f"  {icon} {sig_type:<7s} {t:>4d}   {c:>4d}   {a:>5.1f}%   {r:>+7.2f}%"
                )

        # --- By grade ---
        by_grade = stats.get("by_grade", {})
        if by_grade:
            lines += [
                "",
                f"  {thin}",
                "  🎯 按评分等级 (A级信号是否更准?)",
                f"  {thin}",
                "  等级     样本   正确   准确率    平均收益",
                f"  {thin}",
            ]
            for grade, bg in sorted(by_grade.items()):
                icon = {"A": "🟢", "B": "🟡"}.get(grade, "🔴")
                t = bg["total"]
                c = bg["correct"]
                a = bg["accuracy"] * 100
                r = bg["avg_return"] * 100
                lines.append(
                    f"  {icon} {grade:<7s} {t:>4d}   {c:>4d}   {a:>5.1f}%   {r:>+7.2f}%"
                )

        # --- By dimension ---
        by_dim = stats.get("by_dimension", {})
        if by_dim:
            lines += [
                "",
                f"  {thin}",
                "  🔬 维度预测力排名 (高分组准确率 - 低分组准确率)",
                f"  {thin}",
            ]
            sorted_dims = sorted(
                by_dim.items(),
                key=lambda x: x[1]["predictive_power"],
                reverse=True,
            )
            for dim_name, dd in sorted_dims:
                pp = dd["predictive_power"]
                ha = dd["high_score_accuracy"] * 100
                la = dd["low_score_accuracy"] * 100
                if pp > 0.05:
                    icon = "🟢"
                elif pp >= -0.05:
                    icon = "🟡"
                else:
                    icon = "🔴"
                lines.append(
                    f"  {icon} {dim_name:<6s} 预测力={pp:+.2f} "
                    f"(高分{ha:.0f}% vs 低分{la:.0f}%)"
                )

        lines.append("")
        lines.append(sep)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Full report generation
    # ------------------------------------------------------------------

    def generate_full_report(self) -> dict:
        """Load signals, enrich with actual prices, compute stats.

        Returns a multi-window result dict:
            {
                "windows": {30: stats, 60: stats, 90: stats, 180: stats},
                "overall": stats,
            }
        """
        records = self.load_pending_signals()

        # Enrich records: parse time_window_prices, set current_price from actual_6m
        enriched = []
        for rec in records:
            # Parse time_window_prices if it's a string
            twp = rec.get("time_window_prices")
            if isinstance(twp, str):
                rec["time_window_prices"] = json.loads(twp)

            # Set current_price from actual_6m (latest available price)
            actual = rec.get("actual_6m")
            if isinstance(actual, dict) and actual.get("actual_price") is not None:
                rec["current_price"] = actual["actual_price"]
                enriched.append(rec)
            elif rec.get("time_window_prices"):
                # Even without actual_6m, include if we have window prices
                enriched.append(rec)

        result: dict = {"windows": {}}

        # Per-window stats
        for w in [30, 60, 90, 180]:
            stats = self.compute_accuracy_stats(enriched, window_days=w)
            if stats.get("total", 0) > 0:
                result["windows"][w] = stats

        # Overall stats (using current_price from actual_6m)
        overall_records = [r for r in enriched if r.get("current_price")]
        result["overall"] = self.compute_accuracy_stats(overall_records)

        return result
