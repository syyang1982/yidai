#!/usr/bin/env python3
"""Quick market snapshot for daily briefing."""
import urllib.request
import json
import sys

# Sina HK stocks
try:
    codes = 'rt_hk01810,rt_hk09988,rt_hk03896,rt_hk03888,rt_hk02252,rt_hk02498,rt_hk09626,rt_hk09999,rt_hk09896,rt_hk02020,rt_hk01361'
    url = f'https://hq.sinajs.cn/list={codes}'
    req = urllib.request.Request(url, headers={'Referer':'https://finance.sina.com.cn'})
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode('gbk')
    print("=== HK Stocks ===")
    for line in data.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('=')
        code = parts[0].split('_')[-1].strip('"')
        fields = parts[1].strip('";\n').split(',')
        if len(fields) > 9:
            name = fields[1]
            price = fields[6]
            pct = fields[8] if len(fields) > 8 else 'N/A'
            print(f'{code} {name}: HK${price} ({pct}%)')
except Exception as e:
    print(f"HK error: {e}")

# US stocks (LX)
try:
    url2 = 'https://hq.sinajs.cn/list=gb_lx'
    req2 = urllib.request.Request(url2, headers={'Referer':'https://finance.sina.com.cn'})
    resp2 = urllib.request.urlopen(req2, timeout=10)
    data2 = resp2.read().decode('gbk')
    print("\n=== US Stocks ===")
    for line in data2.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('=')
        fields = parts[1].strip('";\n').split(',')
        if len(fields) > 1:
            name = fields[0]
            price = fields[1]
            print(f'LX {name}: ${price}')
except Exception as e:
    print(f"US error: {e}")

# Oil & Gold via Sina futures
try:
    url3 = 'https://hq.sinajs.cn/list=hf_GC,hf_CL,hf_SI'
    req3 = urllib.request.Request(url3, headers={'Referer':'https://finance.sina.com.cn'})
    resp3 = urllib.request.urlopen(req3, timeout=10)
    data3 = resp3.read().decode('gbk')
    print("\n=== Futures ===")
    for line in data3.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('=')
        code = parts[0].split('_')[-1]
        fields = parts[1].strip('";\n').split(',')
        if len(fields) > 8:
            price = fields[0]
            pct_field = fields[8] if len(fields) > 8 else ''
            print(f'{code}: {price}')
except Exception as e:
    print(f"Futures error: {e}")
