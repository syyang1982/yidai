"""Signal accuracy audit module.

Audits historical signal accuracy by comparing signal prices
to current prices and checking directional correctness.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import duckdb


DEFAULT_DB_PATH = Path.home() / ".hermes" / "yidai" / "db" / "signals.duckdb"


class AccuracyAuditor:
    """Audits signal accuracy against current prices."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH

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
            actual_6m (from JSON).
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
            "prediction_accuracy",
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

    def compute_accuracy_stats(self, records: list[dict]) -> dict:
        """Compute direction accuracy and return statistics.

        Each record must have ``signal_type``, ``signal_price``,
        and ``current_price`` (the actual observed price).  Optional
        fields: ``grade``, ``dimension_scores``.

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
