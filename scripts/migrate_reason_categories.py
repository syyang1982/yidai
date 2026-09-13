#!/usr/bin/env python3
"""
迁移脚本：为 decision_log 现有记录回填 reason_category 和 sell_reason。

使用 reason_taxonomy.classify_reason() 自动分类，然后写入数据库。

用法：python scripts/migrate_reason_categories.py [--dry-run] [--db PATH]
"""

import argparse
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb
from src.strategy.reason_taxonomy import classify_reason, ReasonCategory, SellReason


def migrate(db_path: str, dry_run: bool = False):
    """回填 reason_category 和 sell_reason。"""
    con = duckdb.connect(db_path, read_only=dry_run)

    # 确保列存在
    existing_cols = {r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'decision_log'"
    ).fetchall()}

    if dry_run:
        print("=== DRY RUN 模式（不修改数据库）===\n")
    else:
        if "reason_category" not in existing_cols:
            con.execute("ALTER TABLE decision_log ADD COLUMN reason_category VARCHAR")
            print("✓ 添加 reason_category 列")
        if "sell_reason" not in existing_cols:
            con.execute("ALTER TABLE decision_log ADD COLUMN sell_reason VARCHAR")
            print("✓ 添加 sell_reason 列")

    # 读取所有记录
    rows = con.execute(
        "SELECT decision_id, action, reason FROM decision_log ORDER BY decision_id"
    ).fetchall()

    print(f"\n共 {len(rows)} 条记录待分类：\n")
    print(f"{'ID':12s} {'动作':8s} {'原始理由':20s} → {'催化剂分类':15s} {'卖出原因':15s}")
    print("-" * 80)

    stats = {"buy_cats": {}, "sell_reasons": {}, "total": 0, "updated": 0}

    for decision_id, action, reason in rows:
        reason_cat, sell_cat = classify_reason(reason or "", action or "BUY")

        cat_label = reason_cat.value if reason_cat else ""
        sell_label = sell_cat.value if sell_cat else ""

        print(f"{decision_id:12s} {action:8s} {(reason or '')[:20]:20s} → {cat_label:15s} {sell_label:15s}")

        if not dry_run:
            con.execute(
                "UPDATE decision_log SET reason_category = ?, sell_reason = ? WHERE decision_id = ?",
                [cat_label, sell_label, decision_id],
            )

        stats["total"] += 1
        stats["updated"] += 1

        if reason_cat:
            stats["buy_cats"][cat_label] = stats["buy_cats"].get(cat_label, 0) + 1
        if sell_cat:
            stats["sell_reasons"][sell_label] = stats["sell_reasons"].get(sell_label, 0) + 1

    con.close()

    # 汇总
    print("\n=== 分类汇总 ===\n")
    print(f"总计: {stats['total']} 条")

    if stats["buy_cats"]:
        print("\n买入催化剂分类:")
        for cat, count in sorted(stats["buy_cats"].items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

    if stats["sell_reasons"]:
        print("\n卖出原因分类:")
        for reason, count in sorted(stats["sell_reasons"].items(), key=lambda x: -x[1]):
            print(f"  {reason}: {count}")

    updated = stats["updated"]
    msg = "DRY RUN 完成，未修改数据库" if dry_run else f"迁移完成，更新 {updated} 条记录"
    print(f"\n{msg}")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回填决策理由分类")
    parser.add_argument("--dry-run", action="store_true", help="只展示分类结果，不写入")
    parser.add_argument("--db", default="db/decisions.duckdb", help="数据库路径")
    args = parser.parse_args()

    migrate(args.db, dry_run=args.dry_run)
