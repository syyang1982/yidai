# 意怠工程 — 三大支柱改进计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**目标:** 通过信号准确率审计、领先指标结构化追踪、组合约束层三项改进，
将意怠工程从"评分工具"升级为"闭环投资决策系统"。

**架构:**
- 支柱1: 新增 `src/analysis/accuracy_audit.py` — 用已有750条信号数据做回溯审计
- 支柱2: 新增 `src/analysis/leading_indicators.py` + DuckDB表 — 将文本领先指标编码为可追踪结构
- 支柱3: 新增 `src/strategy/portfolio_constraints.py` — 组合层面约束检查

**Tech Stack:** Python 3.11+, DuckDB, pytest, 现有src/模块

**数据现状:**
- signals.duckdb: 750条信号记录,30条>3个月(可做部分准确率检查)
- 所有信号有company_state(含price/pe/pb),prediction_6m(含expected_price)
- 无actual_6m数据(需要回填当前价格)
- watchlist.md: 15家公司有文本形式的领先指标
- portfolio_data.json: 13个持仓,小米占比~60%+

---

## 支柱一: 信号准确率审计

### 原理
已有750条信号记录,每条都有发射时的价格(company_state.price)和
预测价格(prediction_6m.expected_price)。只需回填当前价格,就能计算:
- 信号方向准确率(买入后涨了?减仓后跌了?)
- 价格预测偏差(预测vs实际)
- 各评分等级/维度的预测力

### Task 1.1: 创建准确率审计模块骨架

**Objective:** 创建 `src/analysis/accuracy_audit.py` 基础结构

**Files:**
- Create: `src/analysis/accuracy_audit.py`
- Create: `tests/test_analysis/test_accuracy_audit.py`

**Step 1: 写失败测试**

```python
# tests/test_analysis/test_accuracy_audit.py
"""信号准确率审计测试。"""
import json
import pytest
from src.analysis.accuracy_audit import AccuracyAuditor


class TestAccuracyAuditorBasic:
    """基础功能测试。"""

    def test_calculate_return_pct(self):
        """计算收益率: (当前价-信号价)/信号价"""
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)
        ret = auditor._calculate_return_pct(100.0, 110.0)
        assert ret == pytest.approx(0.10)

    def test_calculate_return_pct_zero_signal_price(self):
        """信号价为0时返回None"""
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)
        ret = auditor._calculate_return_pct(0.0, 110.0)
        assert ret is None

    def test_is_direction_correct_buy(self):
        """BUY信号:价格上涨=方向正确"""
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)
        assert auditor._is_direction_correct("BUY", 100.0, 110.0) is True
        assert auditor._is_direction_correct("BUY", 100.0, 90.0) is False

    def test_is_direction_correct_reduce(self):
        """REDUCE信号:价格下跌=方向正确"""
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)
        assert auditor._is_direction_correct("REDUCE", 100.0, 90.0) is True
        assert auditor._is_direction_correct("REDUCE", 100.0, 110.0) is False

    def test_is_direction_correct_hold(self):
        """HOLD信号:涨跌幅<10%算正确(不折腾)"""
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)
        assert auditor._is_direction_correct("HOLD", 100.0, 105.0) is True
        assert auditor._is_direction_correct("HOLD", 100.0, 85.0) is False
```

**Step 2: 运行测试确认失败**

Run: `cd ~/.hermes/yidai && python -m pytest tests/test_analysis/test_accuracy_audit.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: 写最小实现**

```python
# src/analysis/accuracy_audit.py
"""信号准确率审计模块。

回溯分析历史信号的预测准确度,回答核心问题:
- 评分系统真的有预测力吗?
- 哪些维度最准/最不准?
- BUY信号的实际胜率是多少?
"""
from __future__ import annotations
from typing import Optional


class AccuracyAuditor:
    """信号准确率审计器。"""

    def _calculate_return_pct(
        self, signal_price: float, current_price: float
    ) -> Optional[float]:
        """计算从信号价到当前价的收益率。"""
        if not signal_price or signal_price <= 0:
            return None
        return (current_price - signal_price) / signal_price

    def _is_direction_correct(
        self, signal_type: str, signal_price: float, current_price: float
    ) -> bool:
        """判断信号方向是否正确。

        BUY: 价格上涨 = 正确
        REDUCE: 价格下跌 = 正确
        HOLD: 涨跌幅 < 10% = 正确 (不折腾即正确)
        WATCH: 不判断
        """
        ret = self._calculate_return_pct(signal_price, current_price)
        if ret is None:
            return False

        if signal_type == "BUY":
            return ret > 0
        elif signal_type == "REDUCE":
            return ret < 0
        elif signal_type == "HOLD":
            return abs(ret) < 0.10
        return False  # WATCH
```

**Step 4: 运行测试确认通过**

Run: `cd ~/.hermes/yidai && python -m pytest tests/test_analysis/test_accuracy_audit.py -v`
Expected: 5 passed

**Step 5: 提交**

```bash
git add src/analysis/accuracy_audit.py tests/test_analysis/test_accuracy_audit.py
git commit -m "feat(audit): 信号准确率审计模块骨架 + 基础计算"
```

---

### Task 1.2: 从signals.duckdb回填当前价格

**Objective:** 从eastmoney获取信号发射时的当前价格,存入actual_6m字段

**Files:**
- Modify: `src/analysis/accuracy_audit.py`
- Modify: `tests/test_analysis/test_accuracy_audit.py`

**Step 1: 写失败测试**

```python
# 在 test_accuracy_audit.py 中追加

class TestBackfillPrices:
    """回填价格测试。"""

    def test_backfill_reads_signal_records(self, tmp_path):
        """从DuckDB读取信号记录并获取当前价格"""
        import duckdb
        # 创建测试数据库
        db_path = str(tmp_path / "test_signals.duckdb")
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state JSON, dimension_scores JSON,
                total_score INTEGER, grade VARCHAR, analysis_details JSON,
                user_action VARCHAR, user_shares INTEGER, user_price DOUBLE,
                user_date DATE, user_reason VARCHAR,
                prediction_6m JSON, prediction_12m JSON,
                actual_6m JSON, actual_12m JSON,
                prediction_accuracy JSON, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                'test001', '01810.HK', '小米', '2026-05-28', 'BUY', '七维评分',
                '{"price": 20.0, "pe": 10}', '{"盈利": 5}',
                32, 'A', '{}', '', 0, 0, NULL, NULL,
                '{"expected_price": 22.0}', '{"expected_price": 24.0}',
                NULL, NULL, NULL, '', '', 'active_6m',
                '2026-05-28', '2026-05-28'
            )
        """)
        conn.close()

        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor(db_path=db_path)
        records = auditor.load_pending_signals()
        assert len(records) == 1
        assert records[0]["signal_id"] == "test001"
        assert records[0]["signal_price"] == 20.0
```

**Step 2: 运行测试确认失败**

Run: `cd ~/.hermes/yidai && python -m pytest tests/test_analysis/test_accuracy_audit.py::TestBackfillPrices -v`

**Step 3: 实现load_pending_signals**

```python
# 在 AccuracyAuditor 类中添加

import duckdb
import json
from datetime import date


class AccuracyAuditor:
    """信号准确率审计器。"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            import os
            db_path = os.path.join(
                os.path.expanduser("~"), ".hermes", "yidai", "db", "signals.duckdb"
            )
        self.db_path = db_path

    def load_pending_signals(self, min_days_old: int = 0) -> list[dict]:
        """加载待审计的信号记录。

        Args:
            min_days_old: 只加载至少N天前的信号(需要足够时间观察)

        Returns:
            list of dicts with signal_id, ticker, signal_type, signal_date,
            signal_price, expected_price, total_score, grade, dimension_scores
        """
        conn = duckdb.connect(self.db_path, read_only=True)
        try:
            rows = conn.execute("""
                SELECT signal_id, ticker, company_name, signal_date,
                       signal_type, company_state, dimension_scores,
                       total_score, grade, prediction_6m, actual_6m
                FROM signal_records
                WHERE status != 'completed'
                ORDER BY signal_date
            """).fetchall()
        finally:
            conn.close()

        results = []
        for row in rows:
            state = json.loads(row[5]) if row[5] else {}
            pred_6m = json.loads(row[9]) if row[9] else {}
            actual_6m = json.loads(row[10]) if row[10] else None

            signal_date = row[3]
            if hasattr(signal_date, 'isoformat'):
                signal_date = signal_date.isoformat()

            results.append({
                "signal_id": row[0],
                "ticker": row[1],
                "company_name": row[2],
                "signal_date": signal_date,
                "signal_type": row[4],
                "signal_price": state.get("price", 0),
                "expected_price_6m": pred_6m.get("expected_price", 0),
                "total_score": row[7],
                "grade": row[8],
                "dimension_scores": json.loads(row[6]) if row[6] else {},
                "actual_6m": actual_6m,
            })
        return results
```

**Step 4: 运行测试确认通过**

**Step 5: 提交**

---

### Task 1.3: 实现准确率统计引擎

**Objective:** 计算整体/分组/分维度的信号准确率

**Files:**
- Modify: `src/analysis/accuracy_audit.py`
- Modify: `tests/test_analysis/test_accuracy_audit.py`

**Step 1: 写失败测试**

```python
class TestAccuracyStats:
    """准确率统计测试。"""

    def test_overall_accuracy(self):
        """整体方向准确率计算"""
        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)

        records = [
            {"signal_type": "BUY", "signal_price": 100, "current_price": 110},  # correct
            {"signal_type": "BUY", "signal_price": 100, "current_price": 90},   # wrong
            {"signal_type": "REDUCE", "signal_price": 100, "current_price": 80}, # correct
            {"signal_type": "HOLD", "signal_price": 100, "current_price": 105},  # correct
        ]
        result = auditor.compute_accuracy_stats(records)
        assert result["total"] == 4
        assert result["correct"] == 3
        assert result["direction_accuracy"] == pytest.approx(0.75)

    def test_accuracy_by_signal_type(self):
        """按信号类型分组统计"""
        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)

        records = [
            {"signal_type": "BUY", "signal_price": 100, "current_price": 110},
            {"signal_type": "BUY", "signal_price": 100, "current_price": 120},
            {"signal_type": "REDUCE", "signal_price": 100, "current_price": 110},  # wrong
        ]
        result = auditor.compute_accuracy_stats(records)
        assert result["by_type"]["BUY"]["accuracy"] == pytest.approx(1.0)
        assert result["by_type"]["REDUCE"]["accuracy"] == pytest.approx(0.0)

    def test_accuracy_by_grade(self):
        """按评分等级分组统计 — A级信号是否比C级更准?"""
        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)

        records = [
            {"signal_type": "BUY", "signal_price": 100, "current_price": 110,
             "grade": "A", "total_score": 33},
            {"signal_type": "BUY", "signal_price": 100, "current_price": 90,
             "grade": "C", "total_score": 18},
        ]
        result = auditor.compute_accuracy_stats(records)
        assert result["by_grade"]["A"]["accuracy"] == pytest.approx(1.0)
        assert result["by_grade"]["C"]["accuracy"] == pytest.approx(0.0)

    def test_accuracy_by_dimension(self):
        """维度级准确率 — 哪个维度评分高时信号更准?"""
        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)

        records = [
            {"signal_type": "BUY", "signal_price": 100, "current_price": 110,
             "dimension_scores": {"盈利": 5, "估值": 2, "成长": 4}},
            {"signal_type": "BUY", "signal_price": 100, "current_price": 90,
             "dimension_scores": {"盈利": 2, "估值": 5, "成长": 1}},
        ]
        result = auditor.compute_accuracy_stats(records)
        # 盈利维度: 高分(5)的信号正确,低分(2)的错误 → 高分组准确率100%
        assert "by_dimension" in result
```

**Step 2-3: 实现compute_accuracy_stats**

```python
def compute_accuracy_stats(self, records: list[dict]) -> dict:
    """计算信号准确率统计。

    Args:
        records: list of dicts, each must have:
            signal_type, signal_price, current_price
            Optional: grade, total_score, dimension_scores

    Returns:
        dict with:
            - total, correct, direction_accuracy
            - by_type: {BUY: {total, correct, accuracy}, ...}
            - by_grade: {A: {total, correct, accuracy}, ...}
            - by_dimension: {dim_name: {high: {acc}, low: {acc}}, ...}
            - avg_return_pct: 平均收益率
            - by_type_avg_return: {BUY: avg_return, ...}
    """
    total = 0
    correct = 0
    returns = []
    by_type = {}
    by_grade = {}
    dim_buckets = {}  # dim -> {high: [bool], low: [bool]}

    for rec in records:
        sig_type = rec.get("signal_type", "")
        sig_price = rec.get("signal_price", 0)
        cur_price = rec.get("current_price", 0)

        if not sig_price or not cur_price:
            continue

        ret = self._calculate_return_pct(sig_price, cur_price)
        is_correct = self._is_direction_correct(sig_type, sig_price, cur_price)

        total += 1
        if is_correct:
            correct += 1
        if ret is not None:
            returns.append(ret)

        # by signal type
        if sig_type not in by_type:
            by_type[sig_type] = {"total": 0, "correct": 0, "returns": []}
        by_type[sig_type]["total"] += 1
        if is_correct:
            by_type[sig_type]["correct"] += 1
        if ret is not None:
            by_type[sig_type]["returns"].append(ret)

        # by grade
        grade = rec.get("grade")
        if grade:
            if grade not in by_grade:
                by_grade[grade] = {"total": 0, "correct": 0, "returns": []}
            by_grade[grade]["total"] += 1
            if is_correct:
                by_grade[grade]["correct"] += 1
            if ret is not None:
                by_grade[grade]["returns"].append(ret)

        # by dimension (split at score 3: high>=3, low<3)
        dims = rec.get("dimension_scores", {})
        for dim_name, dim_score in dims.items():
            bucket = "high" if dim_score >= 3 else "low"
            if dim_name not in dim_buckets:
                dim_buckets[dim_name] = {"high": [], "low": []}
            dim_buckets[dim_name][bucket].append(is_correct)

    # Compute percentages
    def _acc(d):
        return d["correct"] / d["total"] if d["total"] > 0 else 0

    def _avg(lst):
        return sum(lst) / len(lst) if lst else 0

    result = {
        "total": total,
        "correct": correct,
        "direction_accuracy": correct / total if total > 0 else 0,
        "avg_return_pct": _avg(returns),
        "by_type": {},
        "by_grade": {},
        "by_dimension": {},
    }

    for sig_type, data in by_type.items():
        result["by_type"][sig_type] = {
            "total": data["total"],
            "correct": data["correct"],
            "accuracy": _acc(data),
            "avg_return": _avg(data["returns"]),
        }

    for grade, data in by_grade.items():
        result["by_grade"][grade] = {
            "total": data["total"],
            "correct": data["correct"],
            "accuracy": _acc(data),
            "avg_return": _avg(data["returns"]),
        }

    for dim_name, buckets in dim_buckets.items():
        high_acc = sum(buckets["high"]) / len(buckets["high"]) if buckets["high"] else 0
        low_acc = sum(buckets["low"]) / len(buckets["low"]) if buckets["low"] else 0
        result["by_dimension"][dim_name] = {
            "high_score_accuracy": high_acc,
            "low_score_accuracy": low_acc,
            "high_count": len(buckets["high"]),
            "low_count": len(buckets["low"]),
            "predictive_power": high_acc - low_acc,  # 正值=有预测力
        }

    return result
```

**Step 4-5: 测试通过 + 提交**

---

### Task 1.4: 实现价格回填脚本

**Objective:** 从eastmoney获取当前价格,回填到signals.duckdb的actual_6m字段

**Files:**
- Modify: `src/analysis/accuracy_audit.py`
- Create: `scripts/backfill_signal_prices.py`

**Step 1: 写失败测试**

```python
class TestBackfill:
    """价格回填测试。"""

    def test_backfill_updates_actual_6m(self, tmp_path):
        """回填后,actual_6m字段应包含当前价格"""
        import duckdb, json
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE signal_records (
                signal_id VARCHAR, ticker VARCHAR, company_name VARCHAR,
                signal_date DATE, signal_type VARCHAR, signal_source VARCHAR,
                company_state JSON, dimension_scores JSON,
                total_score INTEGER, grade VARCHAR, analysis_details JSON,
                user_action VARCHAR, user_shares INTEGER, user_price DOUBLE,
                user_date DATE, user_reason VARCHAR,
                prediction_6m JSON, prediction_12m JSON,
                actual_6m JSON, actual_12m JSON,
                prediction_accuracy JSON, lessons_learned VARCHAR,
                system_improvement VARCHAR, status VARCHAR,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO signal_records VALUES (
                't1', '01810.HK', '小米', '2026-05-28', 'BUY', '七维评分',
                '{"price": 20.0}', '{}', 32, 'A', '{}',
                '', 0, 0, NULL, NULL,
                '{"expected_price": 22.0}', NULL, NULL, NULL,
                NULL, '', '', 'active_6m', '2026-05-28', '2026-05-28'
            )
        """)
        conn.close()

        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor(db_path=db_path)

        # Mock price fetcher
        class MockFetcher:
            def fetch_price_hk(self, code):
                return {"close_price": 25.0}

        auditor.backfill_prices(fetcher=MockFetcher())

        # Verify
        conn = duckdb.connect(db_path, read_only=True)
        row = conn.execute("SELECT actual_6m FROM signal_records WHERE signal_id='t1'").fetchone()
        conn.close()
        actual = json.loads(row[0])
        assert actual["actual_price"] == 25.0
        assert "backfill_date" in actual
```

**Step 2-3: 实现backfill_prices**

```python
def backfill_prices(self, fetcher=None, max_records: int = 100) -> int:
    """回填信号的当前价格到actual_6m。

    Args:
        fetcher: EastmoneyFetcher实例(测试时可mock)
        max_records: 单次最大处理数

    Returns:
        成功回填的记录数
    """
    if fetcher is None:
        from src.data.fetcher import EastmoneyFetcher
        fetcher = EastmoneyFetcher()

    conn = duckdb.connect(self.db_path)
    try:
        rows = conn.execute("""
            SELECT signal_id, ticker, company_state
            FROM signal_records
            WHERE actual_6m IS NULL
            ORDER BY signal_date
            LIMIT ?
        """, [max_records]).fetchall()

        updated = 0
        today = date.today().isoformat()

        for row in rows:
            signal_id, ticker, state_json = row
            state = json.loads(state_json) if state_json else {}
            signal_price = state.get("price", 0)

            if not signal_price:
                continue

            try:
                market, code = fetcher._detect_market(ticker)
                if market == "hk":
                    price_data = fetcher.fetch_price_hk(code)
                elif market == "a_share":
                    price_data = fetcher.fetch_price_a_share(code)
                else:
                    price_data = fetcher.fetch_price_us(code)

                current_price = price_data.get("close_price")
                if not current_price:
                    continue

                actual = json.dumps({
                    "actual_price": current_price,
                    "backfill_date": today,
                }, ensure_ascii=False)

                conn.execute("""
                    UPDATE signal_records
                    SET actual_6m = ?, updated_at = ?
                    WHERE signal_id = ?
                """, [actual, today, signal_id])
                updated += 1

            except Exception as e:
                logger.warning("Failed to backfill %s: %s", ticker, e)

        conn.commit()
        return updated
    finally:
        conn.close()
```

**Step 4: 创建独立脚本**

```python
#!/usr/bin/env python3
# scripts/backfill_signal_prices.py
"""回填信号价格并生成准确率报告。"""
import sys, os
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
```

**Step 5: 测试通过 + 提交**

---

### Task 1.5: 实现格式化报告输出

**Objective:** 生成可读的准确率审计报告(终端+Markdown)

**Files:**
- Modify: `src/analysis/accuracy_audit.py`
- Modify: `tests/test_analysis/test_accuracy_audit.py`

**Step 1: 写失败测试**

```python
class TestReportFormat:
    """报告格式测试。"""

    def test_format_report_contains_sections(self):
        """报告应包含关键区块"""
        from src.analysis.accuracy_audit import AccuracyAuditor
        auditor = AccuracyAuditor.__new__(AccuracyAuditor)

        stats = {
            "total": 100, "correct": 65,
            "direction_accuracy": 0.65,
            "avg_return_pct": 0.03,
            "by_type": {
                "BUY": {"total": 30, "correct": 22, "accuracy": 0.73, "avg_return": 0.08},
                "HOLD": {"total": 50, "correct": 35, "accuracy": 0.70, "avg_return": 0.01},
                "REDUCE": {"total": 20, "correct": 8, "accuracy": 0.40, "avg_return": -0.02},
            },
            "by_grade": {
                "A": {"total": 20, "correct": 17, "accuracy": 0.85, "avg_return": 0.12},
                "B": {"total": 50, "correct": 33, "accuracy": 0.66, "avg_return": 0.03},
                "C": {"total": 30, "correct": 15, "accuracy": 0.50, "avg_return": -0.01},
            },
            "by_dimension": {
                "盈利": {"high_score_accuracy": 0.72, "low_score_accuracy": 0.55,
                         "predictive_power": 0.17, "high_count": 60, "low_count": 40},
            },
        }
        report = auditor.format_report(stats)
        assert "整体方向准确率" in report
        assert "按信号类型" in report
        assert "按评分等级" in report
        assert "维度预测力" in report
        assert "BUY" in report
```

**Step 2-3: 实现format_report**

```python
def format_report(self, stats: dict) -> str:
    """格式化准确率审计报告。"""
    lines = []
    lines.append("=" * 60)
    lines.append("  📊 信号准确率审计报告")
    lines.append("=" * 60)

    # 整体
    total = stats.get("total", 0)
    acc = stats.get("direction_accuracy", 0)
    avg_ret = stats.get("avg_return_pct", 0)
    acc_icon = "🟢" if acc >= 0.6 else "🟡" if acc >= 0.5 else "🔴"

    lines.append(f"\n  {acc_icon} 整体方向准确率: {acc:.1%} ({stats.get('correct',0)}/{total})")
    lines.append(f"  📈 平均收益率: {avg_ret:+.2%}")
    lines.append(f"  📊 样本量: {total} 条信号")

    # 按信号类型
    lines.append(f"\n  {'─' * 50}")
    lines.append("  📋 按信号类型")
    lines.append(f"  {'─' * 50}")
    lines.append(f"  {'类型':<8} {'样本':>6} {'正确':>6} {'准确率':>8} {'平均收益':>10}")
    lines.append(f"  {'─' * 50}")
    for sig_type in ["BUY", "HOLD", "WATCH", "REDUCE"]:
        data = stats.get("by_type", {}).get(sig_type)
        if not data:
            continue
        icon = "🟢" if data["accuracy"] >= 0.6 else "🟡" if data["accuracy"] >= 0.5 else "🔴"
        lines.append(
            f"  {icon} {sig_type:<6} {data['total']:>6} {data['correct']:>6} "
            f"{data['accuracy']:>7.1%} {data['avg_return']:>+9.2%}"
        )

    # 按评分等级
    lines.append(f"\n  {'─' * 50}")
    lines.append("  🎯 按评分等级 (A级信号是否更准?)")
    lines.append(f"  {'─' * 50}")
    lines.append(f"  {'等级':<8} {'样本':>6} {'正确':>6} {'准确率':>8} {'平均收益':>10}")
    lines.append(f"  {'─' * 50}")
    for grade in ["A", "B", "C", "D", "F"]:
        data = stats.get("by_grade", {}).get(grade)
        if not data:
            continue
        icon = "🟢" if data["accuracy"] >= 0.6 else "🟡" if data["accuracy"] >= 0.5 else "🔴"
        lines.append(
            f"  {icon} {grade:<6} {data['total']:>6} {data['correct']:>6} "
            f"{data['accuracy']:>7.1%} {data['avg_return']:>+9.2%}"
        )

    # 维度预测力排名
    dims = stats.get("by_dimension", {})
    if dims:
        lines.append(f"\n  {'─' * 50}")
        lines.append("  🔬 维度预测力排名 (高分组准确率 - 低分组准确率)")
        lines.append(f"  {'─' * 50}")
        sorted_dims = sorted(dims.items(), key=lambda x: x[1].get("predictive_power", 0), reverse=True)
        for dim_name, dim_data in sorted_dims:
            pp = dim_data.get("predictive_power", 0)
            icon = "🟢" if pp > 0.1 else "🟡" if pp > 0 else "🔴"
            lines.append(
                f"  {icon} {dim_name:<8} 预测力={pp:+.2f} "
                f"(高分{dim_data.get('high_score_accuracy',0):.0%} vs "
                f"低分{dim_data.get('low_score_accuracy',0):.0%})"
            )

    lines.append(f"\n{'=' * 60}")
    return "\n".join(lines)

def generate_full_report(self) -> dict:
    """加载数据,计算统计,返回完整报告数据。"""
    records = self.load_pending_signals()
    # 回填价格(如果有actual_6m就用,否则用fetcher)
    enriched = []
    for rec in records:
        if rec.get("actual_6m") and rec["actual_6m"].get("actual_price"):
            rec["current_price"] = rec["actual_6m"]["actual_price"]
            enriched.append(rec)
        elif rec.get("signal_price"):
            # 没有actual_6m的跳过(需要先运行backfill)
            pass
    return self.compute_accuracy_stats(enriched)
```

**Step 4-5: 测试通过 + 提交**

---

### Task 1.6: 集成到manage.py和周报

**Objective:** 添加 `manage.py audit` 命令,在周报中显示准确率摘要

**Files:**
- Modify: `manage.py` (追加cmd_audit函数)
- Modify: `src/report/weekly_v2.py` (追加准确率区块)

**Step 1:** 在manage.py中添加命令(约15行)

**Step 2:** 在weekly_v2.py的generate_report_v2中追加:
```python
# 准确率摘要
from src.analysis.accuracy_audit import AccuracyAuditor
auditor = AccuracyAuditor()
stats = auditor.generate_full_report()
if stats.get("total", 0) > 0:
    # 在周报中显示1-2行摘要
    acc = stats.get("direction_accuracy", 0)
    lines.append(f"\n# 📈 信号准确率: {acc:.1%} ({stats.get('correct',0)}/{stats.get('total',0)})")
```

**Step 3-5: 测试 + 集成测试 + 提交**

---

## 支柱二: 领先指标结构化追踪

### 原理
watchlist.md中15家公司已有文本形式的领先指标(如"星网月发射>30颗"、
"季度产能利用率趋势")。需要:
1. 从文本提取为结构化数据
2. 存入DuckDB
3. 周报自动检查是否触发

### Task 2.1: 设计领先指标数据模型

**Objective:** 创建leading_indicators.py + DuckDB表结构

**Files:**
- Create: `src/analysis/leading_indicators.py`
- Create: `tests/test_analysis/test_leading_indicators.py`

**Step 1: 写失败测试**

```python
# tests/test_analysis/test_leading_indicators.py
"""领先指标追踪测试。"""
import json
import pytest
from src.analysis.leading_indicators import LeadingIndicatorStore


class TestLeadingIndicatorStore:
    """领先指标存储测试。"""

    def test_create_table(self, tmp_path):
        """创建leading_indicators表"""
        import duckdb
        db_path = str(tmp_path / "test.duckdb")
        store = LeadingIndicatorStore(db_path)
        # 验证表存在
        conn = duckdb.connect(db_path, read_only=True)
        tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
        conn.close()
        assert "leading_indicators" in tables

    def test_add_indicator(self, tmp_path):
        """添加一条领先指标"""
        import duckdb
        db_path = str(tmp_path / "test.duckdb")
        store = LeadingIndicatorStore(db_path)

        store.add_indicator(
            ticker="001270.SZ",
            name="铖昌科技",
            indicator_name="星网月发射数",
            description="星网卫星月发射数量,>30颗为积极信号",
            source="季报/公告",
            threshold_positive=30,
            threshold_negative=None,
            unit="颗/月",
            category="业务指标",
        )

        indicators = store.get_indicators("001270.SZ")
        assert len(indicators) == 1
        assert indicators[0]["indicator_name"] == "星网月发射数"
        assert indicators[0]["threshold_positive"] == 30

    def test_update_value(self, tmp_path):
        """更新指标值"""
        import duckdb
        db_path = str(tmp_path / "test.duckdb")
        store = LeadingIndicatorStore(db_path)

        store.add_indicator(
            ticker="001270.SZ", name="铖昌科技",
            indicator_name="星网月发射数",
            description="月发射数量", source="公告",
            threshold_positive=30, unit="颗/月",
        )

        store.update_value("001270.SZ", "星网月发射数", 35, "2026-07")

        indicators = store.get_indicators("001270.SZ")
        assert indicators[0]["latest_value"] == 35
        assert indicators[0]["latest_period"] == "2026-07"
        assert indicators[0]["status"] == "positive"  # 35 > 30

    def test_status_calculation(self, tmp_path):
        """根据阈值自动计算状态"""
        import duckdb
        db_path = str(tmp_path / "test.duckdb")
        store = LeadingIndicatorStore(db_path)

        store.add_indicator(
            ticker="001270.SZ", name="铖昌科技",
            indicator_name="营收增速",
            description="季度营收同比增速",
            source="季报", threshold_positive=30,
            threshold_negative=10, unit="%",
        )

        # 高于positive阈值 → positive
        store.update_value("001270.SZ", "营收增速", 40, "2026-Q1")
        ind = store.get_indicators("001270.SZ")[0]
        assert ind["status"] == "positive"

        # 低于negative阈值 → negative
        store.update_value("001270.SZ", "营收增速", 5, "2026-Q2")
        ind = store.get_indicators("001270.SZ")[0]
        assert ind["status"] == "negative"

        # 介于两者之间 → neutral
        store.update_value("001270.SZ", "营收增速", 20, "2026-Q3")
        ind = store.get_indicators("001270.SZ")[0]
        assert ind["status"] == "neutral"
```

**Step 2-3: 实现LeadingIndicatorStore**

```python
# src/analysis/leading_indicators.py
"""领先指标结构化追踪系统。

将watchlist.md中散落的文本领先指标编码为可追踪的结构化数据,
支持:
- 添加/更新指标定义
- 记录指标值(按期)
- 自动判断状态(positive/negative/neutral)
- 集成到周报
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional

import duckdb


class LeadingIndicatorStore:
    """领先指标存储。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leading_indicators (
                    ticker VARCHAR NOT NULL,
                    company_name VARCHAR,
                    indicator_name VARCHAR NOT NULL,
                    description VARCHAR,
                    source VARCHAR,
                    threshold_positive DOUBLE,
                    threshold_negative DOUBLE,
                    unit VARCHAR,
                    category VARCHAR DEFAULT '业务指标',
                    latest_value DOUBLE,
                    latest_period VARCHAR,
                    latest_date DATE,
                    status VARCHAR DEFAULT 'unknown',
                    notes VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, indicator_name)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def add_indicator(
        self,
        ticker: str,
        name: str,
        indicator_name: str,
        description: str = "",
        source: str = "",
        threshold_positive: float = None,
        threshold_negative: float = None,
        unit: str = "",
        category: str = "业务指标",
    ) -> None:
        """添加或更新一条领先指标定义。"""
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO leading_indicators
                (ticker, company_name, indicator_name, description, source,
                 threshold_positive, threshold_negative, unit, category,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, [ticker, name, indicator_name, description, source,
                  threshold_positive, threshold_negative, unit, category])
            conn.commit()
        finally:
            conn.close()

    def update_value(
        self,
        ticker: str,
        indicator_name: str,
        value: float,
        period: str,
    ) -> None:
        """更新指标值,自动计算状态。"""
        conn = duckdb.connect(self.db_path)
        try:
            row = conn.execute("""
                SELECT threshold_positive, threshold_negative
                FROM leading_indicators
                WHERE ticker = ? AND indicator_name = ?
            """, [ticker, indicator_name]).fetchone()

            if not row:
                raise ValueError(f"指标不存在: {ticker}/{indicator_name}")

            tp, tn = row
            status = "unknown"
            if tp is not None and value >= tp:
                status = "positive"
            elif tn is not None and value <= tn:
                status = "negative"
            elif tp is not None and tn is not None:
                status = "neutral"

            conn.execute("""
                UPDATE leading_indicators SET
                    latest_value = ?, latest_period = ?,
                    latest_date = CURRENT_DATE, status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ticker = ? AND indicator_name = ?
            """, [value, period, status, ticker, indicator_name])
            conn.commit()
        finally:
            conn.close()

    def get_indicators(self, ticker: str = None) -> list[dict]:
        """获取指标列表,可按ticker过滤。"""
        conn = duckdb.connect(self.db_path, read_only=True)
        try:
            if ticker:
                rows = conn.execute("""
                    SELECT * FROM leading_indicators WHERE ticker = ?
                    ORDER BY indicator_name
                """, [ticker]).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM leading_indicators
                    ORDER BY ticker, indicator_name
                """).fetchall()

            cols = [d[0] for d in conn.execute(
                "SELECT * FROM leading_indicators LIMIT 0"
            ).description]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            conn.close()

    def get_alerts(self) -> list[dict]:
        """获取需要关注的指标(负面状态或长期未更新)。"""
        indicators = self.get_indicators()
        alerts = []
        for ind in indicators:
            if ind.get("status") == "negative":
                alerts.append({
                    "type": "negative",
                    "ticker": ind["ticker"],
                    "company": ind["company_name"],
                    "indicator": ind["indicator_name"],
                    "value": ind["latest_value"],
                    "threshold": ind["threshold_negative"],
                    "message": f"{ind['company_name']}: {ind['indicator_name']}={ind['latest_value']}{ind.get('unit','')} "
                               f"低于阈值{ind['threshold_negative']}{ind.get('unit','')}",
                })
            elif ind.get("status") == "unknown":
                alerts.append({
                    "type": "no_data",
                    "ticker": ind["ticker"],
                    "company": ind["company_name"],
                    "indicator": ind["indicator_name"],
                    "message": f"{ind['company_name']}: {ind['indicator_name']} 暂无数据",
                })
        return alerts
```

**Step 4-5: 测试通过 + 提交**

---

### Task 2.2: 从watchlist.md批量导入领先指标

**Objective:** 解析watchlist.md中的15个领先指标,自动导入DuckDB

**Files:**
- Create: `scripts/import_leading_indicators.py`

**Step 1: 写脚本**

```python
#!/usr/bin/env python3
"""从watchlist.md提取领先指标并导入DuckDB。"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.leading_indicators import LeadingIndicatorStore

# 手动编码的领先指标(从watchlist.md提取)
INDICATORS = [
    # 铖昌科技
    {"ticker": "001270.SZ", "name": "铖昌科技", "indicators": [
        {"indicator_name": "星网月发射数", "description": "星网卫星月发射数量", "source": "公告",
         "threshold_positive": 30, "unit": "颗/月", "category": "业务指标"},
        {"indicator_name": "营收增速", "description": "季度营收同比增速", "source": "季报",
         "threshold_positive": 30, "threshold_negative": 10, "unit": "%", "category": "财务指标"},
        {"indicator_name": "应收账款周转天数", "description": "应收账款/营收*365", "source": "季报",
         "threshold_positive": None, "threshold_negative": 180, "unit": "天", "category": "财务指标"},
    ]},
    # 来福谐波
    {"ticker": "301528.SZ", "name": "来福谐波", "indicators": [
        {"indicator_name": "月度出货量", "description": "谐波减速器月出货量趋势", "source": "月度数据",
         "threshold_positive": None, "unit": "台", "category": "业务指标"},
        {"indicator_name": "新客户导入数", "description": "新导入的机器人客户数", "source": "公告",
         "threshold_positive": 3, "unit": "家/季度", "category": "业务指标"},
    ]},
    # 海康威视
    {"ticker": "002415.SZ", "name": "海康威视", "indicators": [
        {"indicator_name": "营收增速", "description": "季度营收同比增速", "source": "季报",
         "threshold_positive": 5, "threshold_negative": 0, "unit": "%", "category": "财务指标"},
        {"indicator_name": "海外收入占比", "description": "海外收入/总收入", "source": "季报",
         "threshold_positive": 35, "unit": "%", "category": "结构指标"},
        {"indicator_name": "创新业务收入占比", "description": "创新业务/总收入", "source": "季报",
         "threshold_positive": 20, "unit": "%", "category": "结构指标"},
    ]},
    # 英维克
    {"ticker": "002837.SZ", "name": "英维克", "indicators": [
        {"indicator_name": "液冷订单增速", "description": "液冷业务订单同比增速", "source": "季报",
         "threshold_positive": 50, "unit": "%", "category": "业务指标"},
        {"indicator_name": "液冷收入占比", "description": "液冷收入/总收入", "source": "季报",
         "threshold_positive": 30, "unit": "%", "category": "结构指标"},
    ]},
    # 海光信息
    {"ticker": "688041.SH", "name": "海光信息", "indicators": [
        {"indicator_name": "DCU出货量", "description": "季度DCU出货量", "source": "季报",
         "threshold_positive": None, "unit": "颗", "category": "业务指标"},
    ]},
    # 工业富联
    {"ticker": "601138.SS", "name": "工业富联", "indicators": [
        {"indicator_name": "AI服务器毛利率", "description": "AI服务器制造毛利率", "source": "季报",
         "threshold_positive": 8, "threshold_negative": 5, "unit": "%", "category": "财务指标"},
    ]},
    # 中际旭创
    {"ticker": "300308.SZ", "name": "中际旭创", "indicators": [
        {"indicator_name": "800G出货量", "description": "800G光模块季度出货量", "source": "季报",
         "threshold_positive": None, "unit": "只", "category": "业务指标"},
    ]},
    # 中创新航
    {"ticker": "03931.HK", "name": "中创新航", "indicators": [
        {"indicator_name": "产能利用率", "description": "季度产能利用率", "source": "季报",
         "threshold_positive": 80, "threshold_negative": 60, "unit": "%", "category": "运营指标"},
        {"indicator_name": "小米车型交付量", "description": "供应小米的电池交付量", "source": "公告",
         "threshold_positive": None, "unit": "套", "category": "业务指标"},
    ]},
    # 永辉超市
    {"ticker": "601933.SH", "name": "永辉超市", "indicators": [
        {"indicator_name": "同店增长率", "description": "改造门店同店销售增长率", "source": "季报",
         "threshold_positive": 10, "threshold_negative": 0, "unit": "%", "category": "运营指标"},
        {"indicator_name": "毛利率", "description": "综合毛利率", "source": "季报",
         "threshold_positive": 22, "threshold_negative": 20, "unit": "%", "category": "财务指标"},
    ]},
    # 万国数据
    {"ticker": "09698.HK", "name": "万国数据", "indicators": [
        {"indicator_name": "季度新签MW", "description": "季度新签IT容量", "source": "季报",
         "threshold_positive": 100, "unit": "MW", "category": "业务指标"},
        {"indicator_name": "AI客户收入占比", "description": "AI客户收入/总收入", "source": "季报",
         "threshold_positive": 40, "unit": "%", "category": "结构指标"},
        {"indicator_name": "上架率", "description": "IT容量上架率", "source": "季报",
         "threshold_positive": 75, "unit": "%", "category": "运营指标"},
    ]},
    # 赣锋锂业
    {"ticker": "002460.SZ", "name": "赣锋锂业", "indicators": [
        {"indicator_name": "碳酸锂价格", "description": "电池级碳酸锂现货价", "source": "市场数据",
         "threshold_positive": 100000, "threshold_negative": 70000, "unit": "元/吨", "category": "商品价格"},
        {"indicator_name": "毛利率", "description": "综合毛利率(困境反转指标)", "source": "季报",
         "threshold_positive": 20, "threshold_negative": 5, "unit": "%", "category": "财务指标"},
    ]},
    # 杭氧股份
    {"ticker": "002430.SZ", "name": "杭氧股份", "indicators": [
        {"indicator_name": "提氦项目招标数", "description": "国内新提氦项目招标数量", "source": "行业数据",
         "threshold_positive": 5, "unit": "个/半年", "category": "行业指标"},
    ]},
]

def main():
    db_path = os.path.join(os.path.expanduser("~"), ".hermes", "yidai", "db", "yidai.duckdb")
    store = LeadingIndicatorStore(db_path)

    total = 0
    for company in INDICATORS:
        ticker = company["ticker"]
        name = company["name"]
        for ind in company["indicators"]:
            store.add_indicator(
                ticker=ticker, name=name, **ind
            )
            total += 1
            print(f"  ✅ {name}: {ind['indicator_name']}")

    print(f"\n共导入 {total} 条领先指标")

if __name__ == "__main__":
    main()
```

**Step 2: 运行导入**

Run: `cd ~/.hermes/yidai && python scripts/import_leading_indicators.py`

**Step 3: 验证**

```python
# 验证导入结果
store = LeadingIndicatorStore(db_path)
all_indicators = store.get_indicators()
print(f"总计 {len(all_indicators)} 条领先指标")
```

**Step 4: 提交**

---

### Task 2.3: 集成到周报和manage.py

**Objective:** 在周报中显示领先指标状态,添加 `manage.py indicators` 命令

**Files:**
- Modify: `src/report/weekly_v2.py`
- Modify: `manage.py`

**Step 1:** 在周报中追加领先指标区块:

```python
def _render_leading_indicators(store) -> str:
    """渲染领先指标区块。"""
    from src.analysis.leading_indicators import LeadingIndicatorStore
    try:
        li_store = LeadingIndicatorStore(store.db_path)
        indicators = li_store.get_indicators()
        alerts = li_store.get_alerts()
    except Exception:
        return ""

    if not indicators:
        return ""

    lines = ["# 📡 领先指标追踪", ""]

    # Alerts first
    negative = [a for a in alerts if a["type"] == "negative"]
    no_data = [a for a in alerts if a["type"] == "no_data"]

    if negative:
        lines.append("## ⚠️ 触发预警")
        for a in negative:
            lines.append(f"- 🔴 {a['message']}")
        lines.append("")

    if no_data:
        lines.append("## ❓ 待更新")
        for a in no_data[:5]:  # 最多显示5个
            lines.append(f"- {a['message']}")
        lines.append("")

    # Summary by ticker
    lines.append("## 指标总览")
    lines.append("")
    lines.append("| 公司 | 指标 | 最新值 | 阈值 | 状态 |")
    lines.append("|------|------|--------|------|------|")

    for ind in indicators:
        if ind.get("latest_value") is None:
            status_icon = "❓"
            val_str = "—"
        elif ind["status"] == "positive":
            status_icon = "🟢"
            val_str = f"{ind['latest_value']}{ind.get('unit','')}"
        elif ind["status"] == "negative":
            status_icon = "🔴"
            val_str = f"{ind['latest_value']}{ind.get('unit','')}"
        else:
            status_icon = "🟡"
            val_str = f"{ind['latest_value']}{ind.get('unit','')}"

        tp = ind.get("threshold_positive")
        tn = ind.get("threshold_negative")
        threshold_str = ""
        if tp and tn:
            threshold_str = f"{tn}-{tp}{ind.get('unit','')}"
        elif tp:
            threshold_str = f"≥{tp}{ind.get('unit','')}"
        elif tn:
            threshold_str = f"≤{tn}{ind.get('unit','')}"

        lines.append(
            f"| {ind['company_name']} | {ind['indicator_name']} | "
            f"{val_str} | {threshold_str} | {status_icon} |"
        )

    lines.append("")
    lines.append("---")
    return "\n".join(lines)
```

**Step 2:** 在manage.py中添加命令:
```python
def cmd_indicators(args):
    """领先指标管理。"""
    from src.analysis.leading_indicators import LeadingIndicatorStore
    db_path = os.path.join(PROJECT_ROOT, "db", "yidai.duckdb")
    store = LeadingIndicatorStore(db_path)

    if args.ticker:
        indicators = store.get_indicators(args.ticker)
    else:
        indicators = store.get_indicators()

    # 格式化输出...
```

**Step 3-5: 测试 + 提交**

---

## 支柱三: 组合约束层

### 原理
当前系统逐股评分,没有组合层面视角。需要检查:
- 单股仓位上限(如≤25%)
- 行业集中度(如单行业≤40%)
- 市场暴露(如港股≤70%)
- 高相关性持仓(如小米+金山云)

### Task 3.1: 创建组合约束模块

**Objective:** 实现 `src/strategy/portfolio_constraints.py`

**Files:**
- Create: `src/strategy/portfolio_constraints.py`
- Create: `tests/test_strategy/test_portfolio_constraints.py`

**Step 1: 写失败测试**

```python
# tests/test_strategy/test_portfolio_constraints.py
"""组合约束测试。"""
import pytest
from src.strategy.portfolio_constraints import PortfolioConstraints


class TestPositionLimits:
    """仓位限制测试。"""

    def test_single_position_over_limit(self):
        """单股仓位超过上限应告警"""
        pc = PortfolioConstraints(max_single_pct=25)

        holdings = [
            {"ticker": "01810.HK", "name": "小米", "value_hkd": 600000},
            {"ticker": "9988.HK", "name": "阿里", "value_hkd": 400000},
        ]
        violations = pc.check_position_limits(holdings)
        assert len(violations) == 1
        assert violations[0]["ticker"] == "01810.HK"
        assert violations[0]["actual_pct"] == pytest.approx(60.0)

    def test_all_within_limit(self):
        """所有仓位在限内,无告警"""
        pc = PortfolioConstraints(max_single_pct=30)
        holdings = [
            {"ticker": "A", "name": "A公司", "value_hkd": 250000},
            {"ticker": "B", "name": "B公司", "value_hkd": 250000},
            {"ticker": "C", "name": "C公司", "value_hkd": 250000},
            {"ticker": "D", "name": "D公司", "value_hkd": 250000},
        ]
        violations = pc.check_position_limits(holdings)
        assert len(violations) == 0


class TestSectorConcentration:
    """行业集中度测试。"""

    def test_sector_over_concentrated(self):
        """单行业超过上限"""
        pc = PortfolioConstraints(max_sector_pct=40)
        holdings = [
            {"ticker": "01810.HK", "name": "小米", "value_hkd": 300000, "sector": "互联网"},
            {"ticker": "9988.HK", "name": "阿里", "value_hkd": 300000, "sector": "互联网"},
            {"ticker": "2097.HK", "name": "蜜雪", "value_hkd": 400000, "sector": "消费"},
        ]
        violations = pc.check_sector_concentration(holdings)
        assert len(violations) == 1
        assert violations[0]["sector"] == "互联网"
        assert violations[0]["actual_pct"] == pytest.approx(60.0)


class TestMarketExposure:
    """市场暴露测试。"""

    def test_market_over_exposed(self):
        """单一市场暴露过高"""
        pc = PortfolioConstraints(max_market_pct=70)
        holdings = [
            {"ticker": "01810.HK", "name": "小米", "value_hkd": 400000, "market": "HK"},
            {"ticker": "9988.HK", "name": "阿里", "value_hkd": 300000, "market": "HK"},
            {"ticker": "SGP.ASX", "name": "Stockland", "value_hkd": 100000, "market": "ASX"},
        ]
        violations = pc.check_market_exposure(holdings)
        assert len(violations) == 1
        assert violations[0]["market"] == "HK"


class TestCorrelationGroup:
    """相关性持仓测试。"""

    def test_correlated_positions_detected(self):
        """高相关性持仓应被标记"""
        pc = PortfolioConstraints()
        pc.add_correlation_group(
            "金山系", ["3888.HK", "3896.HK"],
            reason="同一控股公司(金山集团)"
        )
        pc.add_correlation_group(
            "小米生态", ["01810.HK", "3896.HK"],
            reason="小米是金山云大客户"
        )

        holdings = [
            {"ticker": "01810.HK", "value_hkd": 400000},
            {"ticker": "3888.HK", "value_hkd": 200000},
            {"ticker": "3896.HK", "value_hkd": 100000},
            {"ticker": "2097.HK", "value_hkd": 300000},
        ]
        warnings = pc.check_correlation_groups(holdings)
        assert len(warnings) >= 1
        # 金山系: 3888+3896 = 300K/1M = 30%
        # 小米生态: 01810+3896 = 500K/1M = 50%
```

**Step 2-3: 实现PortfolioConstraints**

```python
# src/strategy/portfolio_constraints.py
"""组合约束检查模块。

在信号层面(而非事后)检查组合风险:
- 单股仓位上限
- 行业集中度上限
- 市场暴露上限
- 高相关性持仓组
"""
from __future__ import annotations
from typing import List, Dict, Optional


class PortfolioConstraints:
    """组合约束检查器。"""

    def __init__(
        self,
        max_single_pct: float = 25.0,
        max_sector_pct: float = 40.0,
        max_market_pct: float = 70.0,
        max_correlation_group_pct: float = 35.0,
    ):
        self.max_single_pct = max_single_pct
        self.max_sector_pct = max_sector_pct
        self.max_market_pct = max_market_pct
        self.max_correlation_group_pct = max_correlation_group_pct
        self._correlation_groups: List[dict] = []

    def add_correlation_group(
        self, name: str, tickers: List[str], reason: str = ""
    ) -> None:
        """添加一组高相关性持仓。"""
        self._correlation_groups.append({
            "name": name,
            "tickers": tickers,
            "reason": reason,
        })

    def check_position_limits(self, holdings: List[dict]) -> List[dict]:
        """检查单股仓位是否超限。

        Args:
            holdings: list of dicts with 'ticker', 'name', 'value_hkd'

        Returns:
            list of violation dicts
        """
        total = sum(h.get("value_hkd", 0) for h in holdings)
        if total <= 0:
            return []

        violations = []
        for h in holdings:
            pct = h.get("value_hkd", 0) / total * 100
            if pct > self.max_single_pct:
                violations.append({
                    "type": "position_limit",
                    "ticker": h.get("ticker"),
                    "name": h.get("name"),
                    "actual_pct": round(pct, 1),
                    "limit_pct": self.max_single_pct,
                    "excess_pct": round(pct - self.max_single_pct, 1),
                    "message": f"{h.get('name')} 仓位 {pct:.1f}% 超过上限 {self.max_single_pct:.0f}%",
                })
        return violations

    def check_sector_concentration(self, holdings: List[dict]) -> List[dict]:
        """检查行业集中度。"""
        total = sum(h.get("value_hkd", 0) for h in holdings)
        if total <= 0:
            return []

        sector_values = {}
        for h in holdings:
            sector = h.get("sector", "未分类")
            sector_values[sector] = sector_values.get(sector, 0) + h.get("value_hkd", 0)

        violations = []
        for sector, value in sector_values.items():
            pct = value / total * 100
            if pct > self.max_sector_pct:
                violations.append({
                    "type": "sector_concentration",
                    "sector": sector,
                    "actual_pct": round(pct, 1),
                    "limit_pct": self.max_sector_pct,
                    "message": f"{sector} 行业占比 {pct:.1f}% 超过上限 {self.max_sector_pct:.0f}%",
                })
        return violations

    def check_market_exposure(self, holdings: List[dict]) -> List[dict]:
        """检查单一市场暴露。"""
        total = sum(h.get("value_hkd", 0) for h in holdings)
        if total <= 0:
            return []

        market_values = {}
        for h in holdings:
            market = h.get("market", "未知")
            market_values[market] = market_values.get(market, 0) + h.get("value_hkd", 0)

        violations = []
        for market, value in market_values.items():
            pct = value / total * 100
            if pct > self.max_market_pct:
                violations.append({
                    "type": "market_exposure",
                    "market": market,
                    "actual_pct": round(pct, 1),
                    "limit_pct": self.max_market_pct,
                    "message": f"{market} 市场占比 {pct:.1f}% 超过上限 {self.max_market_pct:.0f}%",
                })
        return violations

    def check_correlation_groups(self, holdings: List[dict]) -> List[dict]:
        """检查高相关性持仓组的合计暴露。"""
        total = sum(h.get("value_hkd", 0) for h in holdings)
        if total <= 0:
            return []

        ticker_values = {h.get("ticker"): h.get("value_hkd", 0) for h in holdings}

        warnings = []
        for group in self._correlation_groups:
            group_value = sum(
                ticker_values.get(t, 0) for t in group["tickers"]
            )
            pct = group_value / total * 100
            if pct > self.max_correlation_group_pct:
                warnings.append({
                    "type": "correlation_group",
                    "group_name": group["name"],
                    "tickers": group["tickers"],
                    "reason": group["reason"],
                    "actual_pct": round(pct, 1),
                    "limit_pct": self.max_correlation_group_pct,
                    "message": f"关联组「{group['name']}」合计 {pct:.1f}% "
                               f"超过上限 {self.max_correlation_group_pct:.0f}% "
                               f"({group['reason']})",
                })
        return warnings

    def check_all(self, holdings: List[dict]) -> dict:
        """运行所有约束检查,返回汇总结果。"""
        violations = []
        violations.extend(self.check_position_limits(holdings))
        violations.extend(self.check_sector_concentration(holdings))
        violations.extend(self.check_market_exposure(holdings))
        violations.extend(self.check_correlation_groups(holdings))

        total_value = sum(h.get("value_hkd", 0) for h in holdings)

        return {
            "total_value": total_value,
            "position_count": len(holdings),
            "violations": violations,
            "violation_count": len(violations),
            "has_violations": len(violations) > 0,
        }

    def format_report(self, result: dict) -> str:
        """格式化约束检查报告。"""
        lines = []
        lines.append("=" * 55)
        lines.append("  🛡️ 组合约束检查")
        lines.append("=" * 55)

        lines.append(f"\n  持仓数: {result['position_count']}")
        lines.append(f"  总市值: {result['total_value']:,.0f} HKD")

        if not result["has_violations"]:
            lines.append("\n  ✅ 所有约束检查通过")
        else:
            lines.append(f"\n  ⚠️ 发现 {result['violation_count']} 项违规:")
            for v in result["violations"]:
                icon = {"position_limit": "📊", "sector_concentration": "🏭",
                        "market_exposure": "🌍", "correlation_group": "🔗"
                        }.get(v["type"], "⚠️")
                lines.append(f"  {icon} {v['message']}")

        lines.append(f"\n{'=' * 55}")
        return "\n".join(lines)
```

**Step 4-5: 测试通过 + 提交**

---

### Task 3.2: 配置当前持仓的约束规则

**Objective:** 基于portfolio_data.json配置实际的约束规则和相关性组

**Files:**
- Create: `src/strategy/portfolio_config.py`
- Modify: `manage.py` (添加constraints命令)

**Step 1: 创建配置**

```python
# src/strategy/portfolio_config.py
"""意怠工程组合约束配置。"""
from src.strategy.portfolio_constraints import PortfolioConstraints


def get_default_constraints() -> PortfolioConstraints:
    """返回默认约束配置。"""
    pc = PortfolioConstraints(
        max_single_pct=25.0,      # 单股不超25%
        max_sector_pct=40.0,      # 单行业不超40%
        max_market_pct=70.0,      # 单市场不超70%
        max_correlation_group_pct=35.0,  # 关联组不超35%
    )

    # 高相关性持仓组
    pc.add_correlation_group(
        "金山系", ["3888.HK", "3896.HK"],
        reason="同一控股公司(金山集团)"
    )
    pc.add_correlation_group(
        "小米生态", ["01810.HK", "3896.HK"],
        reason="小米是金山云核心客户+股东"
    )
    pc.add_correlation_group(
        "港股互联网", ["01810.HK", "9988.HK", "9999.HK", "9626.HK"],
        reason="港股互联网板块,受同一宏观因素影响"
    )
    pc.add_correlation_group(
        "港股消费", ["2097.HK", "9896.HK", "1361.HK"],
        reason="港股消费板块"
    )

    return pc
```

**Step 2:** 在manage.py中添加命令:
```python
def cmd_constraints(args):
    """组合约束检查。"""
    from src.strategy.portfolio_config import get_default_constraints
    import json

    pc = get_default_constraints()

    # 从portfolio_data.json加载持仓
    pf_path = os.path.join(os.path.expanduser("~"), ".hermes", "portfolio_data.json")
    with open(pf_path) as f:
        pf_data = json.load(f)

    holdings = _enrich_holdings_with_values(pf_data)  # 需要计算HKD价值
    result = pc.check_all(holdings)
    print(pc.format_report(result))
```

**Step 3-5: 测试 + 集成 + 提交**

---

### Task 3.3: 集成到周报和仪表盘

**Objective:** 在周报和dashboard中显示约束检查结果

**Files:**
- Modify: `src/report/weekly_v2.py`
- Modify: `src/viz/dashboard.py` (已有限度提示,可增强)

**Step 1:** 在周报中追加约束检查区块(约20行代码)

**Step 2:** dashboard.py的 `_extract_risks` 已有集中度检查,
增强为使用PortfolioConstraints做更精确的检查

**Step 3-5: 测试 + 提交**

---

## 实施顺序与依赖

```
Week 1: 支柱一 (信号准确率审计)
  Day 1: Task 1.1 → 1.2 (骨架 + 回填)
  Day 2: Task 1.3 → 1.4 (统计引擎 + 回填脚本)
  Day 3: Task 1.5 → 1.6 (报告 + 集成)

Week 2: 支柱二 (领先指标追踪)
  Day 1: Task 2.1 (数据模型)
  Day 2: Task 2.2 (批量导入)
  Day 3: Task 2.3 (周报集成)

Week 3: 支柱三 (组合约束层)
  Day 1: Task 3.1 (约束模块)
  Day 2: Task 3.2 (配置)
  Day 3: Task 3.3 (集成)

Week 4: 端到端测试 + ROADMAP更新
  - 全流程集成测试
  - 更新ROADMAP.md
  - 生成第一份带准确率+领先指标+约束检查的周报
```

## 验收标准

1. **信号准确率审计:**
   - `python manage.py audit` 可运行,输出格式化报告
   - 报告包含: 整体准确率、按类型/等级/维度分组统计
   - 周报中显示准确率摘要

2. **领先指标追踪:**
   - 15家公司的领先指标已导入DuckDB
   - `python manage.py indicators` 可查看所有指标状态
   - 周报中显示领先指标区块(含预警)

3. **组合约束层:**
   - `python manage.py constraints` 可运行约束检查
   - 能检测到小米仓位超限(当前~60% > 25%)
   - 能检测到金山系关联组超限
   - 周报中显示约束检查结果

---

更新日期: 2026-08-28
