"""Tests for quarterly financial data processing."""

import pytest
from src.analysis.quarterly import (
    filter_periods,
    compute_yoy_growth,
    is_annual,
    get_period_label,
    handle_cumulative,
    prepare_scoring_data,
)


SAMPLE_FINANCIALS = [
    {'period': '2024-09-30', 'revenue': 900, 'net_income': 90},
    {'period': '2024-06-30', 'revenue': 600, 'net_income': 60},
    {'period': '2024-03-31', 'revenue': 300, 'net_income': 30},
    {'period': '2023-12-31', 'revenue': 1200, 'net_income': 120},
    {'period': '2024-12-31', 'revenue': 1600, 'net_income': 160},
    {'period': '2023-09-30', 'revenue': 800, 'net_income': 80},
    {'period': '2023-06-30', 'revenue': 500, 'net_income': 50},
    {'period': '2023-03-31', 'revenue': 250, 'net_income': 25},
]


class TestFilterPeriods:
    def test_annual(self):
        result = filter_periods(SAMPLE_FINANCIALS, mode='annual')
        periods = [f['period'] for f in result]
        assert periods == ['2023-12-31', '2024-12-31']

    def test_quarterly(self):
        result = filter_periods(SAMPLE_FINANCIALS, mode='quarterly')
        periods = [f['period'] for f in result]
        assert '2024-12-31' not in periods
        assert '2023-12-31' not in periods
        assert len(periods) == 6  # 3 per year

    def test_all(self):
        result = filter_periods(SAMPLE_FINANCIALS, mode='all')
        assert len(result) == 8

    def test_sorted_ascending(self):
        result = filter_periods(SAMPLE_FINANCIALS, mode='all')
        periods = [f['period'] for f in result]
        assert periods == sorted(periods)


class TestComputeYoyGrowth:
    def test_matching_quarter(self):
        result = compute_yoy_growth(SAMPLE_FINANCIALS, '2024-09-30', 'revenue')
        # (900 - 800) / 800 = 0.125
        assert abs(result - 0.125) < 1e-9

    def test_missing_previous(self):
        # 2023-03-31 has no 2022-03-31 in data
        result = compute_yoy_growth(SAMPLE_FINANCIALS, '2023-03-31', 'revenue')
        assert result == 0.0

    def test_net_income_yoy(self):
        result = compute_yoy_growth(SAMPLE_FINANCIALS, '2024-06-30', 'net_income')
        # (60 - 50) / 50 = 0.20
        assert abs(result - 0.20) < 1e-9

    def test_annual_yoy(self):
        result = compute_yoy_growth(SAMPLE_FINANCIALS, '2024-12-31', 'revenue')
        # (1600 - 1200) / 1200 = 0.333...
        assert abs(result - (1600 - 1200) / 1200) < 1e-9


class TestIsAnnual:
    def test_annual(self):
        assert is_annual('2024-12-31') is True

    def test_q1(self):
        assert is_annual('2024-03-31') is False

    def test_h1(self):
        assert is_annual('2024-06-30') is False

    def test_q3(self):
        assert is_annual('2024-09-30') is False


class TestGetPeriodLabel:
    def test_fy(self):
        assert get_period_label('2024-12-31') == 'FY2024'

    def test_q1(self):
        assert get_period_label('2024-03-31') == 'Q1-2024'

    def test_h1(self):
        assert get_period_label('2024-06-30') == 'H1-2024'

    def test_q3(self):
        assert get_period_label('2024-09-30') == 'Q3-2024'


class TestHandleCumulative:
    def test_cumulative_conversion(self):
        # Simulate cumulative Chinese GAAP data
        cumulative_financials = [
            {'period': '2024-03-31', 'revenue': 300, 'net_income': 30},
            {'period': '2024-06-30', 'revenue': 700, 'net_income': 65},  # H1 cumulative
            {'period': '2024-09-30', 'revenue': 1100, 'net_income': 100},  # Q3 cumulative
            {'period': '2024-12-31', 'revenue': 1600, 'net_income': 160},
        ]
        result = handle_cumulative(cumulative_financials)
        
        result_by_period = {f['period']: f for f in result}
        
        # Q1 unchanged
        assert result_by_period['2024-03-31']['revenue'] == 300
        assert result_by_period['2024-03-31']['data_quality'] == 'standalone'
        
        # H1 standalone = 700 - 300 = 400
        assert result_by_period['2024-06-30']['revenue'] == 400
        assert result_by_period['2024-06-30']['data_quality'] == 'standalone'
        
        # Q3 standalone = 1100 - 700 - 300 = 100
        assert result_by_period['2024-09-30']['revenue'] == 100
        assert result_by_period['2024-09-30']['data_quality'] == 'standalone'

    def test_non_cumulative_data(self):
        # Non-cumulative: Q2 revenue < Q1 (e.g., seasonal)
        financials = [
            {'period': '2024-03-31', 'revenue': 500, 'net_income': 50},
            {'period': '2024-06-30', 'revenue': 300, 'net_income': 30},
            {'period': '2024-09-30', 'revenue': 400, 'net_income': 40},
        ]
        result = handle_cumulative(financials)
        # Should not modify values, just mark as unknown
        by_period = {f['period']: f for f in result}
        assert by_period['2024-03-31']['revenue'] == 500
        assert by_period['2024-03-31']['data_quality'] == 'unknown'


class TestPrepareScoringData:
    def test_yoy_mode(self):
        fin = {
            'period': '2024-09-30',
            'revenue': 900, 'net_income': 90, 'gross_profit': 450,
            'total_assets': 5000, 'total_liabilities': 2000, 'shareholders_equity': 3000,
        }
        prev = {
            'period': '2023-09-30',
            'revenue': 800, 'net_income': 80, 'gross_profit': 400,
            'total_assets': 4500, 'total_liabilities': 1800, 'shareholders_equity': 2700,
        }
        data = prepare_scoring_data(fin, prev, mode='yoy')
        
        assert data['revenue'] == 900
        assert abs(data['gross_margin'] - 0.5) < 1e-9
        assert abs(data['revenue_growth'] - 0.125) < 1e-9
        assert abs(data['roe'] - 0.03) < 1e-9
        assert data['growth_mode'] == 'yoy'

    def test_sequential_mode(self):
        fin = {
            'period': '2024-06-30',
            'revenue': 600, 'net_income': 60, 'gross_profit': 300,
            'total_assets': 4800, 'total_liabilities': 1900, 'shareholders_equity': 2900,
        }
        prev = {
            'period': '2024-03-31',
            'revenue': 300, 'net_income': 30, 'gross_profit': 150,
        }
        data = prepare_scoring_data(fin, prev, mode='sequential')
        
        assert data['revenue'] == 600
        assert abs(data['revenue_growth'] - 1.0) < 1e-9  # doubled
        assert data['growth_mode'] == 'sequential'

    def test_no_prev(self):
        fin = {
            'period': '2024-03-31',
            'revenue': 300, 'net_income': 30,
            'total_assets': 4000, 'total_liabilities': 1500, 'shareholders_equity': 2500,
        }
        data = prepare_scoring_data(fin, mode='yoy')
        
        assert 'revenue_growth' not in data  # no prev means no growth computed
        assert data['revenue'] == 300
