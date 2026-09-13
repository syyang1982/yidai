#!/usr/bin/env python3
"""把失效观测指标注册到 leading_indicators.duckdb（持仓规范代码）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.leading_indicators import LeadingIndicatorStore
from src.strategy.invalidation_watch import sync, format_watch
from src.strategy.position import PositionBook, default_decision_db
from src.strategy.decision import DecisionLog


def main():
    store = LeadingIndicatorStore()
    stats = sync(store)
    print(f"registered={stats['registered']} seeded={stats['seeded']} copied={stats['copied']}")
    db = default_decision_db()
    log = DecisionLog(db)
    book = PositionBook(db_path=db, conn=log.conn)
    print()
    print(format_watch(store, book.list_open()))


if __name__ == "__main__":
    main()
