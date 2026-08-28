#!/usr/bin/env python3
"""Run the enhanced weekly report generator."""
import sys
sys.path.insert(0, "/home/frank/.hermes/yidai")

from src.report.weekly_v2 import generate_report_v2

path = generate_report_v2(
    db_path="/home/frank/.hermes/yidai/db/yidai.duckdb",
    output_dir="/home/frank/.hermes/yidai/reports",
)
print("REPORT_PATH:", path)
