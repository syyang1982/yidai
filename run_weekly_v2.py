#!/usr/bin/env python3
"""生成增强版周报 v2"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from src.report.weekly_v2 import generate_report_v2

home = os.path.expanduser("~")
db_path = os.path.join(home, ".hermes", "yidai", "db", "yidai.duckdb")
signal_db_path = os.path.join(home, ".hermes", "yidai", "db", "signals.duckdb")
decision_db_path = os.path.join(home, ".hermes", "yidai", "db", "decisions.duckdb")
output_dir = os.path.join(home, ".hermes", "yidai", "reports")

result = generate_report_v2(
    db_path=db_path,
    signal_db_path=signal_db_path,
    decision_db_path=decision_db_path,
    output_dir=output_dir,
)
print(result)
