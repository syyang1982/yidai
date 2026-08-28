"""Quarterly financial data processing helpers."""

from datetime import datetime, timedelta
from typing import Optional


def filter_periods(financials: list[dict], mode: str = 'all') -> list[dict]:
    """Filter financial records by period type.
    
    Args:
        financials: List of financial dicts, each with a 'period' key (e.g. '2024-09-30')
        mode: 'annual' (12-31 only), 'quarterly' (03-31, 06-30, 09-30), 'all'
    
    Returns:
        Filtered list sorted by period ascending.
    """
    if mode == 'annual':
        filtered = [f for f in financials if f.get('period', '').endswith('-12-31')]
    elif mode == 'quarterly':
        filtered = [f for f in financials if f.get('period', '').endswith(('-03-31', '-06-30', '-09-30'))]
    else:
        filtered = list(financials)
    
    return sorted(filtered, key=lambda f: f.get('period', ''))


def compute_yoy_growth(financials: list[dict], current_period: str, field: str = 'revenue') -> float:
    """Compute YoY growth rate for a field.
    
    Args:
        financials: List of financial dicts with 'period' and numeric fields.
        current_period: Period string like '2024-09-30'
        field: Field name to compute growth on (default 'revenue')
    
    Returns:
        Growth rate as decimal (0.25 = 25%), or 0 if previous period not found.
    """
    # Compute previous year period
    try:
        dt = datetime.strptime(current_period, '%Y-%m-%d')
        prev_dt = dt.replace(year=dt.year - 1)
        prev_period = prev_dt.strftime('%Y-%m-%d')
    except (ValueError, OverflowError):
        return 0.0
    
    current_val = None
    prev_val = None
    
    for f in financials:
        if f.get('period') == current_period:
            current_val = f.get(field)
        if f.get('period') == prev_period:
            prev_val = f.get(field)
    
    if current_val is None or prev_val is None or prev_val == 0:
        return 0.0
    
    return (current_val - prev_val) / abs(prev_val)


def is_annual(period: str) -> bool:
    """Returns True if period ends with 12-31."""
    return period.endswith('-12-31')


def get_period_label(period: str) -> str:
    """Returns human-readable label for a period.
    
    Examples:
        '2024-12-31' -> 'FY2024'
        '2024-03-31' -> 'Q1-2024'
        '2024-06-30' -> 'H1-2024'
        '2024-09-30' -> 'Q3-2024'
    """
    suffix_map = {
        '-12-31': lambda y: f'FY{y}',
        '-03-31': lambda y: f'Q1-{y}',
        '-06-30': lambda y: f'H1-{y}',
        '-09-30': lambda y: f'Q3-{y}',
    }
    for suffix, formatter in suffix_map.items():
        if period.endswith(suffix):
            year = period[:4]
            return formatter(year)
    return period


def handle_cumulative(financials: list[dict]) -> list[dict]:
    """Convert cumulative Chinese GAAP figures to standalone quarterly figures.
    
    Chinese quarterly reports are cumulative:
    - Q1: Jan-Mar
    - H1: Jan-Jun (= Q1 + Q2)
    - Q3: Jan-Sep (= Q1 + Q2 + Q3)
    - FY: Jan-Dec (= Q1 + Q2 + Q3 + Q4)
    
    This converts cumulative to standalone where possible.
    
    Returns:
        List of financial dicts with 'data_quality' flag added.
    """
    numeric_fields = ['revenue', 'net_income', 'gross_profit', 'operating_income',
                      'total_expenses', 'ebitda']
    
    # Group by year
    by_year: dict[str, dict[str, dict]] = {}
    for f in financials:
        period = f.get('period', '')
        year = period[:4] if len(period) >= 4 else ''
        suffix = period[5:] if len(period) >= 5 else ''
        by_year.setdefault(year, {})[suffix] = f
    
    result = []
    
    for year in sorted(by_year.keys()):
        periods = by_year[year]
        
        # Detect if data is cumulative by checking revenue monotonicity
        is_cumulative = False
        q1 = periods.get('03-31', {})
        h1 = periods.get('06-30', {})
        q3 = periods.get('09-30', {})
        
        r_q1 = q1.get('revenue')
        r_h1 = h1.get('revenue')
        r_q3 = q3.get('revenue')
        
        if r_q1 is not None and r_h1 is not None and r_q3 is not None:
            if r_q1 > 0 and r_h1 > r_q1 and r_q3 > r_h1:
                is_cumulative = True
        
        for suffix in sorted(periods.keys()):
            f = dict(periods[suffix])
            f.setdefault('period', f'{year}-{suffix}')
            
            if is_cumulative and suffix in ('06-30', '09-30'):
                # Subtract prior cumulative to get standalone
                if suffix == '06-30' and '03-31' in periods:
                    for field in numeric_fields:
                        curr = f.get(field)
                        prev = periods['03-31'].get(field)
                        if curr is not None and prev is not None:
                            f[field] = curr - prev
                    f['data_quality'] = 'standalone'
                elif suffix == '09-30' and '06-30' in periods:
                    for field in numeric_fields:
                        curr = f.get(field)
                        prev_h1 = periods['06-30'].get(field)
                        prev_q1 = periods['03-31'].get(field)
                        if curr is not None and prev_h1 is not None and prev_q1 is not None:
                            # Q3 cumulative is for 9 months, H1 cumulative is for 6 months
                            f[field] = curr - prev_h1 - prev_q1
                        elif curr is not None and prev_h1 is not None:
                            # Fallback: just subtract H1 cumulative
                            f[field] = curr - prev_h1
                    f['data_quality'] = 'standalone'
                else:
                    f['data_quality'] = 'cumulative'
            elif not is_cumulative:
                f['data_quality'] = 'unknown'
            else:
                f['data_quality'] = 'standalone'
            
            result.append(f)
    
    return sorted(result, key=lambda x: x.get('period', ''))


def prepare_scoring_data(fin: dict, prev_fin: Optional[dict] = None, mode: str = 'yoy') -> dict:
    """Prepare a data dict for scoring modules.
    
    Args:
        fin: Current period financial dict
        prev_fin: Previous period (same quarter YoY or sequential) financial dict
        mode: 'yoy' for year-over-year, 'sequential' for period-over-period
    
    Returns:
        Dict with fields needed by profitability.score(), health.score(), etc.
    """
    data = {}
    
    # Copy through common fields
    for key in ['revenue', 'net_income', 'gross_profit', 'operating_income',
                'total_assets', 'total_liabilities', 'shareholders_equity',
                'total_expenses', 'ebitda', 'fcf', 'capex',
                'operating_cash_flow', 'current_assets', 'current_liabilities',
                'period']:
        if key in fin:
            data[key] = fin[key]
    
    # Compute margins
    revenue = fin.get('revenue', 0) or 0
    if revenue:
        data['gross_margin'] = (fin.get('gross_profit', 0) or 0) / revenue
        data['net_margin'] = (fin.get('net_income', 0) or 0) / revenue
        data['operating_margin'] = (fin.get('operating_income', 0) or 0) / revenue
    
    # Compute growth rates
    if prev_fin:
        data['revenue_growth'] = _growth(fin.get('revenue'), prev_fin.get('revenue'))
        data['net_income_growth'] = _growth(fin.get('net_income'), prev_fin.get('net_income'))
        data['gross_profit_growth'] = _growth(fin.get('gross_profit'), prev_fin.get('gross_profit'))
    
    # Compute leverage
    total_assets = fin.get('total_assets', 0) or 0
    total_liabilities = fin.get('total_liabilities', 0) or 0
    equity = fin.get('shareholders_equity', 0) or 0
    
    if total_assets:
        data['debt_to_assets'] = total_liabilities / total_assets
    if equity:
        data['debt_to_equity'] = total_liabilities / equity
        data['roe'] = (fin.get('net_income', 0) or 0) / equity
    if total_assets:
        data['roa'] = (fin.get('net_income', 0) or 0) / total_assets
    
    # Current ratio
    current_assets = fin.get('current_assets')
    current_liabilities = fin.get('current_liabilities')
    if current_assets and current_liabilities:
        data['current_ratio'] = current_assets / current_liabilities
    
    data['growth_mode'] = mode
    
    return data


def _growth(current, previous) -> float:
    """Compute growth rate, returning 0 if previous is missing or zero."""
    if current is None or previous is None or previous == 0:
        return 0.0
    return (current - previous) / abs(previous)
