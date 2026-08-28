"""Signal accuracy audit module.

Audits historical signal accuracy by comparing signal prices
to current prices and checking directional correctness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


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
