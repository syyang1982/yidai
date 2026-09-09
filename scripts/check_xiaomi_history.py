#!/usr/bin/env python3
"""临时脚本：查询小米领先指标历史"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.analysis.leading_indicators import LeadingIndicatorStore

store = LeadingIndicatorStore()
for indicator in ['AI新闻情绪', 'AI产品发布数', 'SU7月交付量']:
    try:
        data = store.get_history('01810.HK', indicator, limit=8)
        print(f'{indicator}:')
        if data:
            for row in data:
                print(f'  {row}')
        else:
            print('  (无历史数据)')
    except Exception as e:
        print(f'{indicator} error: {e}')
