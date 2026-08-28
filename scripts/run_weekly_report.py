"""Run weekly report v2 generation."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.report.weekly_v2 import generate_report_v2

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "yidai.duckdb")
report_path = generate_report_v2(db_path, output_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports"))
print(report_path)
