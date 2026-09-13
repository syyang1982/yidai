"""
预期验证引擎 — 意怠工程 (Yidai)

自动回检决策日志中的预测 vs 实际表现，回答：
1. 预期价格 vs 实际价格的偏差
2. 哪些评分维度有预测力（维度有效性分析）
3. 预警信号的准确性（误报/漏报统计）

设计原则：
- 只读取 DecisionLog + SignalTracker 数据，不修改原始记录
- 生成独立的 ReviewReport，可嵌入周报
- 支持按维度、按公司、按时间段聚合分析
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

import duckdb


@dataclass
class ReviewResult:
    """单条决策的回检结果。"""
    decision_id: str
    ticker: str
    company_name: str
    action: str
    decision_date: str

    # 预测
    expected_price: float = 0.0
    expected_period: str = ""       # "6m" / "12m"

    # 实际
    actual_price: float = 0.0
    actual_return_pct: float = 0.0  # (actual - entry_price) / entry_price * 100
    expected_return_pct: float = 0.0  # (expected - entry_price) / entry_price * 100

    # 准确度
    price_accuracy: float = 0.0     # 1 - |actual - expected| / expected
    direction_correct: bool = False  # 方向是否正确
    beat_expectation: bool = False   # 实际是否超过预期

    # 评分快照
    dimension_scores: dict = field(default_factory=dict)
    total_score: int = 0
    grade: str = ""

    # 元数据
    entry_price: float = 0.0
    status: str = ""


@dataclass
class DimensionEffectiveness:
    """单个评分维度的有效性统计。"""
    dimension: str
    # 高分组（该维度 >= 4）的表现
    high_score_count: int = 0
    high_score_avg_return: float = 0.0
    # 低分组（该维度 <= 2）的表现
    low_score_count: int = 0
    low_score_avg_return: float = 0.0
    # 有效性指标：高分组收益 - 低分组收益（越大越有效）
    effectiveness: float = 0.0


@dataclass
class AlertAccuracy:
    """预警准确性统计。"""
    rule_id: str
    rule_name: str
    total_alerts: int = 0
    true_positives: int = 0    # 预警后确实下跌
    false_positives: int = 0   # 预警后反而上涨
    avg_lead_days: float = 0.0  # 平均提前天数


class ReviewEngine:
    """预期验证引擎。"""

    def __init__(self, db_path: str = None, decision_log: DecisionLog = None):
        if db_path is None:
            db_path = ":memory:"
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._decision_log = decision_log
        self._create_tables()

    def _get_decision_log(self) -> DecisionLog:
        """Get or create a DecisionLog instance."""
        if self._decision_log is not None:
            return self._decision_log
        from src.strategy.decision import DecisionLog
        return DecisionLog(self.db_path)

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS review_results (
                review_id VARCHAR PRIMARY KEY,
                decision_id VARCHAR,
                ticker VARCHAR,
                company_name VARCHAR,
                action VARCHAR,
                decision_date DATE,
                expected_price DOUBLE,
                expected_period VARCHAR,
                actual_price DOUBLE,
                actual_return_pct DOUBLE,
                expected_return_pct DOUBLE,
                price_accuracy DOUBLE,
                direction_correct BOOLEAN,
                beat_expectation BOOLEAN,
                dimension_scores JSON,
                total_score INTEGER,
                grade VARCHAR,
                entry_price DOUBLE,
                status VARCHAR,
                reviewed_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_reviews (
                alert_review_id VARCHAR PRIMARY KEY,
                rule_id VARCHAR,
                ticker VARCHAR,
                alert_date DATE,
                alert_severity VARCHAR,
                price_at_alert DOUBLE,
                price_after_30d DOUBLE,
                price_after_60d DOUBLE,
                price_after_90d DOUBLE,
                return_30d DOUBLE,
                return_60d DOUBLE,
                return_90d DOUBLE,
                was_accurate BOOLEAN,
                created_at TIMESTAMP
            )
        """)

    def review_decision(
        self,
        decision_id: str,
        actual_price: float,
        period: str = "6m",
        fetch_current_fn=None,
    ) -> Optional[ReviewResult]:
        """回检单条决策的预测 vs 实际。

        Args:
            decision_id: 决策ID
            actual_price: 实际价格（如果为0，尝试用fetch_current_fn获取）
            period: "1w" / "1m" / "6m" / "12m"
            fetch_current_fn: 可选的获取当前价格函数 ticker -> price

        Returns:
            ReviewResult 或 None
        """
        dl = self._get_decision_log()
        rec = dl.get(decision_id)
        if not rec:
            return None

        # Determine expected price — 短周期没有预期价格时用 entry price
        if period == "1w":
            expected = rec.expected_price_1w if rec.expected_price_1w > 0 else 0
        elif period == "1m":
            expected = rec.expected_price_1m if rec.expected_price_1m > 0 else 0
        elif period == "6m":
            expected = rec.expected_price_6m
        else:
            expected = rec.expected_price_12m

        entry = rec.price
        if actual_price <= 0 and fetch_current_fn:
            try:
                actual_price = fetch_current_fn(rec.ticker)
            except Exception:
                return None

        if actual_price <= 0 or entry <= 0:
            return None

        # Compute metrics
        actual_ret = (actual_price - entry) / entry * 100
        expected_ret = (expected - entry) / entry * 100 if expected > 0 else 0

        price_acc = 0.0
        if expected > 0:
            price_acc = max(0, 1 - abs(actual_price - expected) / expected)

        direction_ok = (actual_price > entry) == (expected > entry) if expected > 0 else (actual_price > entry)
        beat = actual_price >= expected if expected > 0 else False

        result = ReviewResult(
            decision_id=decision_id,
            ticker=rec.ticker,
            company_name=rec.company_name,
            action=rec.action,
            decision_date=rec.decision_date,
            expected_price=expected,
            expected_period=period,
            actual_price=actual_price,
            actual_return_pct=round(actual_ret, 2),
            expected_return_pct=round(expected_ret, 2),
            price_accuracy=round(price_acc, 4),
            direction_correct=direction_ok,
            beat_expectation=beat,
            dimension_scores=rec.dimension_scores,
            total_score=rec.total_score,
            grade=rec.grade,
            entry_price=entry,
            status="reviewed",
        )

        # Persist
        import uuid
        rid = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO review_results VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            [
                rid, decision_id, rec.ticker, rec.company_name, rec.action,
                rec.decision_date, expected, period, actual_price,
                round(actual_ret, 2), round(expected_ret, 2),
                round(price_acc, 4), direction_ok, beat,
                json.dumps(rec.dimension_scores, ensure_ascii=False),
                rec.total_score, rec.grade, entry, "reviewed", now,
            ],
        )

        # Also update the decision record
        dl.record_outcome(decision_id, actual_price, period)

        return result

    def batch_review(
        self,
        period: str = "6m",
        fetch_current_fn=None,
    ) -> List[ReviewResult]:
        """批量回检所有到期待复盘的决策。"""
        from src.strategy.decision import DecisionLog
        dl = self._get_decision_log()
        pending = dl.get_pending_reviews(period)

        results = []
        for rec in pending:
            if fetch_current_fn:
                try:
                    price = fetch_current_fn(rec.ticker)
                except Exception:
                    continue
                r = self.review_decision(rec.decision_id, price, period)
                if r:
                    results.append(r)
        return results

    def quick_review(
        self,
        period: str = "1w",
        fetch_current_fn=None,
    ) -> List[ReviewResult]:
        """快速复盘：对所有到期的短周期决策进行回检。

        适用于每周/每月运行，提供快速反馈循环。
        与 batch_review 的区别：quick_review 只处理 1w/1m 短周期。

        Args:
            period: "1w" 或 "1m"
            fetch_current_fn: 获取当前价格函数 ticker -> price

        Returns:
            回检结果列表
        """
        if period not in ("1w", "1m"):
            period = "1w"  # 默认1周

        dl = self._get_decision_log()
        pending = dl.get_pending_reviews(period)

        results = []
        for rec in pending:
            if fetch_current_fn:
                try:
                    price = fetch_current_fn(rec.ticker)
                except Exception:
                    continue
                r = self.review_decision(rec.decision_id, price, period)
                if r:
                    results.append(r)
        return results

    def get_quick_review_stats(self, period: str = "1w") -> dict:
        """获取短周期复盘统计。

        Args:
            period: "1w" 或 "1m"

        Returns:
            包含 avg_return, direction_accuracy 等指标的字典
        """
        total = self.conn.execute(
            "SELECT COUNT(*) FROM review_results WHERE expected_period = ?",
            [period]
        ).fetchone()[0]
        if total == 0:
            return {
                "period": period,
                "total_reviews": 0,
                "avg_return": 0,
                "direction_accuracy": 0,
                "positive_rate": 0,
            }

        avg_ret = self.conn.execute(
            """SELECT AVG(actual_return_pct) FROM review_results
               WHERE expected_period = ? AND actual_return_pct != 0""",
            [period]
        ).fetchone()[0]

        dir_correct = self.conn.execute(
            """SELECT COUNT(*) FROM review_results
               WHERE expected_period = ? AND direction_correct = true""",
            [period]
        ).fetchone()[0]

        positive = self.conn.execute(
            """SELECT COUNT(*) FROM review_results
               WHERE expected_period = ? AND actual_return_pct > 0""",
            [period]
        ).fetchone()[0]

        return {
            "period": period,
            "total_reviews": total,
            "avg_return": round(avg_ret, 2) if avg_ret else 0,
            "direction_accuracy": round(dir_correct / total * 100, 1) if total else 0,
            "positive_rate": round(positive / total * 100, 1) if total else 0,
        }

    def analyze_dimension_effectiveness(self) -> List[DimensionEffectiveness]:
        """分析哪些评分维度有预测力。

        逻辑：将决策按每个维度分为高分组(>=4)和低分组(<=2)，
        比较两组的平均实际收益率。差值越大说明该维度越有预测力。
        """
        rows = self.conn.execute(
            """SELECT dimension_scores, actual_return_pct
               FROM review_results
               WHERE actual_return_pct != 0 AND dimension_scores IS NOT NULL"""
        ).fetchall()

        if not rows:
            return []

        dim_returns: Dict[str, Dict[str, list]] = {}

        for scores_json, ret in rows:
            try:
                scores = json.loads(scores_json) if isinstance(scores_json, str) else scores_json
            except (json.JSONDecodeError, TypeError):
                continue
            if not scores:
                continue

            for dim, score in scores.items():
                if dim not in dim_returns:
                    dim_returns[dim] = {"high": [], "low": []}
                if score >= 4:
                    dim_returns[dim]["high"].append(ret)
                elif score <= 2:
                    dim_returns[dim]["low"].append(ret)

        results = []
        for dim, groups in dim_returns.items():
            high = groups["high"]
            low = groups["low"]
            high_avg = sum(high) / len(high) if high else 0
            low_avg = sum(low) / len(low) if low else 0

            results.append(DimensionEffectiveness(
                dimension=dim,
                high_score_count=len(high),
                high_score_avg_return=round(high_avg, 2),
                low_score_count=len(low),
                low_score_avg_return=round(low_avg, 2),
                effectiveness=round(high_avg - low_avg, 2),
            ))

        results.sort(key=lambda x: x.effectiveness, reverse=True)
        return results

    def record_alert_outcome(
        self,
        rule_id: str,
        ticker: str,
        alert_date: str,
        severity: str,
        price_at_alert: float,
        price_after_30d: float = 0,
        price_after_60d: float = 0,
        price_after_90d: float = 0,
    ) -> str:
        """记录预警后的股价表现。"""
        import uuid
        aid = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        ret_30 = (price_after_30d - price_at_alert) / price_at_alert * 100 if price_after_30d > 0 and price_at_alert > 0 else 0
        ret_60 = (price_after_60d - price_at_alert) / price_at_alert * 100 if price_after_60d > 0 and price_at_alert > 0 else 0
        ret_90 = (price_after_90d - price_at_alert) / price_at_alert * 100 if price_after_90d > 0 and price_at_alert > 0 else 0

        # Accurate if price dropped within 90 days after HIGH severity alert
        was_accurate = None
        if severity == "HIGH" and price_after_90d > 0:
            was_accurate = ret_90 < 0
        elif severity == "MEDIUM" and price_after_60d > 0:
            was_accurate = ret_60 < -2  # at least 2% drop

        self.conn.execute(
            """INSERT OR REPLACE INTO alert_reviews VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            [
                aid, rule_id, ticker, alert_date, severity,
                price_at_alert, price_after_30d, price_after_60d, price_after_90d,
                round(ret_30, 2), round(ret_60, 2), round(ret_90, 2),
                was_accurate, now,
            ],
        )
        return aid

    def get_alert_accuracy_stats(self) -> List[AlertAccuracy]:
        """统计各预警规则的准确性。"""
        rows = self.conn.execute(
            """SELECT rule_id, COUNT(*),
                      SUM(CASE WHEN was_accurate = true THEN 1 ELSE 0 END),
                      SUM(CASE WHEN was_accurate = false THEN 1 ELSE 0 END)
               FROM alert_reviews
               WHERE was_accurate IS NOT NULL
               GROUP BY rule_id"""
        ).fetchall()

        results = []
        for rule_id, total, tp, fp in rows:
            # Get rule name from the first alert
            name_row = self.conn.execute(
                "SELECT rule_id FROM alert_reviews WHERE rule_id = ? LIMIT 1",
                [rule_id]
            ).fetchone()
            results.append(AlertAccuracy(
                rule_id=rule_id,
                rule_name=rule_id,  # simplified
                total_alerts=total,
                true_positives=tp,
                false_positives=fp,
            ))
        return results

    def get_review_stats(self) -> dict:
        """汇总回检统计。"""
        total = self.conn.execute("SELECT COUNT(*) FROM review_results").fetchone()[0]
        if total == 0:
            return {
                "total_reviews": 0,
                "direction_accuracy": 0,
                "avg_price_accuracy": 0,
                "avg_return": 0,
                "avg_expected_return": 0,
                "beat_rate": 0,
            }

        dir_correct = self.conn.execute(
            "SELECT COUNT(*) FROM review_results WHERE direction_correct = true"
        ).fetchone()[0]
        avg_price_acc = self.conn.execute(
            "SELECT AVG(price_accuracy) FROM review_results"
        ).fetchone()[0]
        avg_ret = self.conn.execute(
            "SELECT AVG(actual_return_pct) FROM review_results WHERE actual_return_pct != 0"
        ).fetchone()[0]
        avg_exp = self.conn.execute(
            "SELECT AVG(expected_return_pct) FROM review_results WHERE expected_return_pct != 0"
        ).fetchone()[0]
        beats = self.conn.execute(
            "SELECT COUNT(*) FROM review_results WHERE beat_expectation = true"
        ).fetchone()[0]

        return {
            "total_reviews": total,
            "direction_accuracy": round(dir_correct / total * 100, 1) if total else 0,
            "avg_price_accuracy": round(avg_price_acc * 100, 1) if avg_price_acc else 0,
            "avg_return": round(avg_ret, 2) if avg_ret else 0,
            "avg_expected_return": round(avg_exp, 2) if avg_exp else 0,
            "beat_rate": round(beats / total * 100, 1) if total else 0,
        }

    def format_review_report(self, result: ReviewResult) -> str:
        """将单条回检结果格式化为 Markdown。"""
        lines = [
            f"### {result.company_name} ({result.ticker}) — {result.expected_period}回检",
            f"- **决策日期:** {result.decision_date}",
            f"- **操作:** {result.action} @ {result.entry_price}",
            f"- **预期价格:** {result.expected_price}",
            f"- **实际价格:** {result.actual_price}",
            f"- **预期收益:** {result.expected_return_pct:+.1f}%",
            f"- **实际收益:** {result.actual_return_pct:+.1f}%",
            f"- **价格准确度:** {result.price_accuracy*100:.1f}%",
            f"- **方向正确:** {'✅' if result.direction_correct else '❌'}",
            f"- **超越预期:** {'✅' if result.beat_expectation else '❌'}",
        ]
        if result.dimension_scores:
            parts = [f"{k}:{v}" for k, v in result.dimension_scores.items()]
            lines.append(f"- **评分快照:** {' | '.join(parts)} ({result.total_score}/40, {result.grade})")
        return "\n".join(lines)

    def format_dimension_report(self, effectiveness: List[DimensionEffectiveness]) -> str:
        """将维度有效性分析格式化为 Markdown。"""
        if not effectiveness:
            return "  暂无足够数据进行维度有效性分析\n"

        lines = ["### 评分维度有效性分析\n"]
        lines.append(f"  {'维度':<6} {'高分组收益':>10} {'低分组收益':>10} {'有效性':>8} {'判断':<6}")
        lines.append(f"  {'-'*44}")

        for e in effectiveness:
            judge = "✅ 有效" if e.effectiveness > 5 else ("⚠️ 待观察" if e.effectiveness > 0 else "❌ 无效")
            lines.append(
                f"  {e.dimension:<6} {e.high_score_avg_return:>+9.1f}% "
                f"{e.low_score_avg_return:>+9.1f}% {e.effectiveness:>+7.1f}% {judge}"
            )

        return "\n".join(lines)

    def analyze_cognitive_biases(self) -> List[BiasPattern]:
        """检测决策日志中的认知偏差模式。

        检测三种偏差模式：
        1. 过度自信：信心>=4 且 实际收益<-10%
        2. 逆向成功：信心<=2 且 实际收益>+10%（低信心反而赚大钱）
        3. 缺失反面论据：counter_argument为空 且 结果为负

        Returns:
            List[BiasPattern]
        """
        patterns: List[BiasPattern] = []
        dl = self._get_decision_log()
        conn = dl.conn

        # 1. 过度自信模式：高信心 + 亏损
        rows = conn.execute("""
            SELECT decision_id, ticker, company_name, action, decision_date,
                   confidence_level, actual_return_pct, counter_argument
            FROM decision_log
            WHERE confidence_level >= 4
              AND actual_return_pct < -10
              AND actual_return_pct != 0
            ORDER BY actual_return_pct ASC
        """).fetchall()

        if rows:
            avg_ret = sum(r[6] for r in rows) / len(rows)
            examples = [
                {"decision_id": r[0], "ticker": r[1], "company_name": r[2],
                 "confidence": r[5], "return_pct": round(r[6], 1)}
                for r in rows[:5]
            ]
            patterns.append(BiasPattern(
                pattern_type="overconfidence",
                pattern_name="过度自信",
                description=f"信心≥4但亏损>10%，共{len(rows)}笔。平均亏损{avg_ret:.1f}%——高信心不等于高准确率，需警惕确认偏差。",
                count=len(rows),
                avg_return=round(avg_ret, 2),
                examples=examples,
            ))

        # 2. 逆向成功模式：低信心 + 大赚
        rows = conn.execute("""
            SELECT decision_id, ticker, company_name, action, decision_date,
                   confidence_level, actual_return_pct, counter_argument
            FROM decision_log
            WHERE confidence_level <= 2
              AND confidence_level > 0
              AND actual_return_pct > 10
            ORDER BY actual_return_pct DESC
        """).fetchall()

        if rows:
            avg_ret = sum(r[6] for r in rows) / len(rows)
            examples = [
                {"decision_id": r[0], "ticker": r[1], "company_name": r[2],
                 "confidence": r[5], "return_pct": round(r[6], 1)}
                for r in rows[:5]
            ]
            patterns.append(BiasPattern(
                pattern_type="contrarian_success",
                pattern_name="逆向成功",
                description=f"信心≤2但收益>10%，共{len(rows)}笔。平均收益{avg_ret:.1f}%——低信心决策反而表现好，说明直觉可能比分析更准，或存在处置效应。",
                count=len(rows),
                avg_return=round(avg_ret, 2),
                examples=examples,
            ))

        # 3. 缺失反面论据：没写counter_argument + 亏损
        rows = conn.execute("""
            SELECT decision_id, ticker, company_name, action, decision_date,
                   confidence_level, actual_return_pct, counter_argument
            FROM decision_log
            WHERE (counter_argument IS NULL OR counter_argument = '')
              AND actual_return_pct < -5
              AND actual_return_pct != 0
            ORDER BY actual_return_pct ASC
        """).fetchall()

        if rows:
            avg_ret = sum(r[6] for r in rows) / len(rows)
            examples = [
                {"decision_id": r[0], "ticker": r[1], "company_name": r[2],
                 "return_pct": round(r[6], 1)}
                for r in rows[:5]
            ]
            patterns.append(BiasPattern(
                pattern_type="missing_counter_argument",
                pattern_name="缺失反面论据",
                description=f"未写反面论据且亏损>5%，共{len(rows)}笔。平均亏损{avg_ret:.1f}%——未考虑反面论据可能意味着锚定偏差或确认偏差。",
                count=len(rows),
                avg_return=round(avg_ret, 2),
                examples=examples,
            ))

        return patterns

    def format_bias_report(self, patterns: List[BiasPattern]) -> str:
        """将认知偏差检测结果格式化为 Markdown。"""
        if not patterns:
            return "  ✅ 暂未检测到明显认知偏差模式（数据量可能不足）\n"

        lines = ["### 🧠 认知偏差分析报告\n"]

        for p in patterns:
            icon = {
                "overconfidence": "🔴",
                "contrarian_success": "🟢",
                "missing_counter_argument": "🟡",
            }.get(p.pattern_type, "⚪")

            lines.append(f"#### {icon} {p.pattern_name}")
            lines.append(f"- **命中数:** {p.count}笔")
            lines.append(f"- **平均收益:** {p.avg_return:+.1f}%")
            lines.append(f"- **分析:** {p.description}")

            if p.examples:
                lines.append("- **典型案例:**")
                for ex in p.examples:
                    ticker = ex.get("ticker", "?")
                    name = ex.get("company_name", "?")
                    ret = ex.get("return_pct", 0)
                    conf = ex.get("confidence", "?")
                    if p.pattern_type == "missing_counter_argument":
                        lines.append(f"  - {name}({ticker}): 收益{ret:+.1f}%")
                    else:
                        lines.append(f"  - {name}({ticker}): 信心{conf}/5, 收益{ret:+.1f}%")
            lines.append("")

        # 综合建议
        lines.append("#### 💡 改进建议")
        has_overconfidence = any(p.pattern_type == "overconfidence" for p in patterns)
        has_missing = any(p.pattern_type == "missing_counter_argument" for p in patterns)

        if has_overconfidence:
            lines.append("- 🔴 过度自信：高信心决策前做「魔鬼辩护」，列出3个会失败的理由")
        if has_missing:
            lines.append("- 🟡 缺失反面论据：强制要求每个决策填写counter_argument字段")
        if any(p.pattern_type == "contrarian_success" for p in patterns):
            lines.append("- 🟢 逆向成功：低信心时反而赚大钱，考虑是否过度分析导致分析瘫痪")

        return "\n".join(lines)


@dataclass
class BiasPattern:
    """认知偏差检测结果。"""
    pattern_type: str         # "overconfidence" / "contrarian_success" / "missing_counter_argument"
    pattern_name: str         # 中文名称
    description: str          # 偏差描述
    count: int = 0            # 命中该模式的决策数量
    avg_return: float = 0.0   # 命中决策的平均收益率
    examples: list = field(default_factory=list)  # 典型案例
