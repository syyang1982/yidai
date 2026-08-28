#!/usr/bin/env python3
"""回填信号价格并生成准确率报告。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.accuracy_audit import AccuracyAuditor


def main():
    auditor = AccuracyAuditor()
    print("📊 回填信号价格...")
    updated = auditor.backfill_prices(max_records=200)
    print(f"  ✅ 回填 {updated} 条记录")
    print("\n📈 计算准确率统计...")
    stats = auditor.generate_full_report()
    print(auditor.format_report(stats))


if __name__ == "__main__":
    main()
