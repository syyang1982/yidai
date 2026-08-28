#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from src.report.weekly_v2 import generate_report_v2

report_path = generate_report_v2(db_path='db/yidai.duckdb')
print('REPORT_PATH:', report_path)
