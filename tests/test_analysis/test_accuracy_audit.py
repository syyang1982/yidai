"""Tests for the signal accuracy audit module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from analysis.accuracy_audit import AccuracyAuditor


class TestCalculateReturnPct:
    """_calculate_return_pct: (current - signal) / signal."""

    def test_positive_return(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=100.0, current_price=110.0)
        assert result == 0.10

    def test_negative_return(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=100.0, current_price=80.0)
        assert result == -0.20

    def test_zero_return(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=50.0, current_price=50.0)
        assert result == 0.0

    def test_zero_signal_price_returns_none(self):
        auditor = AccuracyAuditor()
        result = auditor._calculate_return_pct(signal_price=0.0, current_price=50.0)
        assert result is None


class TestIsDirectionCorrect:
    """_is_direction_correct: signal type determines what 'correct' means."""

    def test_buy_price_up_is_correct(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="BUY", signal_price=100.0, current_price=110.0
        )
        assert result is True

    def test_buy_price_down_is_incorrect(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="BUY", signal_price=100.0, current_price=90.0
        )
        assert result is False

    def test_reduce_price_down_is_correct(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="REDUCE", signal_price=100.0, current_price=90.0
        )
        assert result is True

    def test_reduce_price_up_is_incorrect(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="REDUCE", signal_price=100.0, current_price=110.0
        )
        assert result is False

    def test_hold_small_change_is_correct(self):
        """HOLD is correct when |return| < 10%."""
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="HOLD", signal_price=100.0, current_price=105.0
        )
        assert result is True

    def test_hold_large_change_is_incorrect(self):
        """HOLD is incorrect when |return| >= 10%."""
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="HOLD", signal_price=100.0, current_price=115.0
        )
        assert result is False

    def test_watch_always_false(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="WATCH", signal_price=100.0, current_price=110.0
        )
        assert result is False

    def test_signal_price_zero_returns_false(self):
        auditor = AccuracyAuditor()
        result = auditor._is_direction_correct(
            signal_type="BUY", signal_price=0.0, current_price=110.0
        )
        assert result is False
