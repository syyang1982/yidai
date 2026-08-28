"""Debug: find correct Alibaba ticker code for eastmoney."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.fetcher import EastmoneyFetcher

f = EastmoneyFetcher()
for code in ['09998', '09988', '9988']:
    try:
        fin = f.fetch_financials(code, periods=2)
        if fin:
            rev = fin[-1].get('revenue', 0)
            period = fin[-1].get('period', '?')
            print(f'{code}: {len(fin)} periods, {period} rev={rev/1e8:.0f}亿')
        else:
            print(f'{code}: no data')
    except Exception as e:
        print(f'{code}: error {e}')
