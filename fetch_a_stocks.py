import sys, os
sys.path.insert(0, '.')
from src.data.fetcher import EastmoneyFetcher
f = EastmoneyFetcher()
targets = ['601600.SH','002460.SZ','603799.SH','600549.SH','002415.SZ','601933.SH','300866.SZ','688017.SZ','301528.SZ','002050.SZ']
for t in targets:
    try:
        p = f.fetch_price(t)
        print(f'{t}: close={p.get("close_price")} PE={p.get("pe_ratio")}')
    except Exception as e:
        print(f'{t}: ERROR {e}')
