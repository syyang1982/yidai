"""
信号追踪与回顾系统

完整的投资信号生命周期管理：
观察 → 分析 → 行动 → 预测 → 结果 → 学习
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional

import duckdb


@dataclass
class SignalRecord:
    """一条信号的完整生命周期记录。"""

    signal_id: str = ""
    ticker: str = ""
    company_name: str = ""

    # Step 1: 信号发射
    signal_date: str = ""
    signal_type: str = ""  # BUY / REDUCE / HOLD / WATCH
    signal_source: str = "七维评分"  # "七维评分" / "趋势过滤" / "手动"

    # Step 2: 信号发射时的公司状态
    company_state: dict = field(default_factory=dict)
    # 包含: price, pe, pb, revenue, net_income, roe, gross_margin,
    #       debt_ratio, ocf, fcf, shares_outstanding, market_cap

    # Step 3: 分析过程
    dimension_scores: dict = field(default_factory=dict)
    total_score: int = 0
    grade: str = ""
    analysis_details: dict = field(default_factory=dict)

    # Step 4: 用户行动
    user_action: str = ""
    user_shares: int = 0
    user_price: float = 0.0
    user_date: str = ""
    user_reason: str = ""

    # Step 5: 预测
    prediction_6m: dict = field(default_factory=dict)
    prediction_12m: dict = field(default_factory=dict)

    # Step 6: 实际结果（后续填写）
    actual_6m: dict = field(default_factory=dict)
    actual_12m: dict = field(default_factory=dict)

    # Step 7: 学习
    prediction_accuracy: dict = field(default_factory=dict)
    lessons_learned: str = ""
    system_improvement: str = ""

    # 元数据
    status: str = "pending"  # pending / active_6m / active_12m / completed
    created_at: str = ""
    updated_at: str = ""


class SignalTracker:
    """信号追踪器：管理投资信号的完整生命周期。"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = ":memory:"
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_records (
                signal_id VARCHAR PRIMARY KEY,
                ticker VARCHAR,
                company_name VARCHAR,
                signal_date DATE,
                signal_type VARCHAR,
                signal_source VARCHAR,
                company_state JSON,
                dimension_scores JSON,
                total_score INTEGER,
                grade VARCHAR,
                analysis_details JSON,
                user_action VARCHAR,
                user_shares INTEGER,
                user_price DOUBLE,
                user_date DATE,
                user_reason VARCHAR,
                prediction_6m JSON,
                prediction_12m JSON,
                actual_6m JSON,
                actual_12m JSON,
                prediction_accuracy JSON,
                lessons_learned VARCHAR,
                system_improvement VARCHAR,
                status VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                time_window_prices JSON
            )
        """)

    def record_signal(
        self,
        ticker: str,
        company_name: str,
        signal_date: str,
        signal_type: str,
        company_state: dict,
        dimension_scores: dict,
        total_score: int,
        grade: str,
        analysis_details: dict,
        signal_source: str = "七维评分",
    ) -> str:
        """记录一条新信号及其完整分析上下文。返回 signal_id。

        同一公司同日重复记录会覆盖旧数据，不产生重复行。
        """
        now = datetime.now().isoformat()

        # 检查当日是否已有该公司的信号记录（按ticker匹配）
        # 先清理同ticker同日的多余记录（保留最新一条）
        self.conn.execute(
            """
            DELETE FROM signal_records
            WHERE ticker = ? AND signal_date = ?
            AND updated_at < (
                SELECT MAX(updated_at) FROM signal_records
                WHERE ticker = ? AND signal_date = ?
            )
            """,
            [ticker, signal_date, ticker, signal_date],
        )
        existing = self.conn.execute(
            "SELECT signal_id FROM signal_records WHERE ticker = ? AND signal_date = ?",
            [ticker, signal_date],
        ).fetchone()

        # 自动预测
        current_price = company_state.get("price", 0)
        revenue = company_state.get("revenue", 0)
        net_income = company_state.get("net_income", 0)

        growth_rate = 0.0
        if revenue and net_income and net_income > 0:
            growth_rate = min((net_income / max(revenue, 1)) * 5, 0.5)

        prediction_6m = {
            "expected_price": round(current_price * (1 + growth_rate * 0.5), 2),
            "expected_score": total_score,
            "expected_grade": grade,
            "expected_signal": signal_type,
            "confidence": 3,
            "reasoning": f"基于当前{grade}评级，假设增长趋势延续6个月",
        }
        prediction_12m = {
            "expected_price": round(current_price * (1 + growth_rate * 1.0), 2),
            "expected_score": total_score,
            "expected_grade": grade,
            "expected_signal": signal_type,
            "confidence": 2,
            "reasoning": f"基于当前{grade}评级，12个月不确定性较大",
        }

        if existing:
            # 覆盖当日已有记录
            signal_id = existing[0]
            self.conn.execute(
                """
                UPDATE signal_records SET
                    ticker = ?, company_name = ?, signal_type = ?, signal_source = ?,
                    company_state = ?, dimension_scores = ?,
                    total_score = ?, grade = ?, analysis_details = ?,
                    prediction_6m = ?, prediction_12m = ?,
                    updated_at = ?
                WHERE signal_id = ?
                """,
                [
                    ticker,
                    company_name,
                    signal_type,
                    signal_source,
                    json.dumps(company_state, ensure_ascii=False),
                    json.dumps(dimension_scores, ensure_ascii=False),
                    total_score,
                    grade,
                    json.dumps(analysis_details, ensure_ascii=False),
                    json.dumps(prediction_6m, ensure_ascii=False),
                    json.dumps(prediction_12m, ensure_ascii=False),
                    now,
                    signal_id,
                ],
            )
        else:
            # 插入新记录
            signal_id = str(uuid.uuid4())[:8]
            self.conn.execute(
                """
                INSERT INTO signal_records VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, NULL, 0, 0, NULL, NULL,
                    ?, ?, NULL, NULL,
                    NULL, '', '', 'active_6m', ?, ?, NULL
                )
                """,
                [
                    signal_id,
                    ticker,
                    company_name,
                    signal_date,
                    signal_type,
                    signal_source,
                    json.dumps(company_state, ensure_ascii=False),
                    json.dumps(dimension_scores, ensure_ascii=False),
                    total_score,
                    grade,
                    json.dumps(analysis_details, ensure_ascii=False),
                    json.dumps(prediction_6m, ensure_ascii=False),
                    json.dumps(prediction_12m, ensure_ascii=False),
                    now,
                    now,
                ],
            )
        return signal_id

    def record_action(
        self,
        signal_id: str,
        user_action: str,
        user_shares: int = 0,
        user_price: float = 0,
        user_date: str = None,
        user_reason: str = "",
    ) -> None:
        """记录用户对信号的实际响应。"""
        if user_date is None:
            user_date = date.today().isoformat()
        now = datetime.now().isoformat()
        self.conn.execute(
            """
            UPDATE signal_records SET
                user_action = ?, user_shares = ?, user_price = ?,
                user_date = ?, user_reason = ?, updated_at = ?
            WHERE signal_id = ?
            """,
            [user_action, user_shares, user_price, user_date, user_reason, now, signal_id],
        )

    def record_prediction(
        self,
        signal_id: str,
        period: str,
        expected_price: float,
        expected_score: int,
        expected_grade: str,
        expected_signal: str,
        confidence: int,
        reasoning: str,
    ) -> None:
        """记录手动预测，覆盖自动生成的预测。period='6m' or '12m'。"""
        pred = {
            "expected_price": expected_price,
            "expected_score": expected_score,
            "expected_grade": expected_grade,
            "expected_signal": expected_signal,
            "confidence": confidence,
            "reasoning": reasoning,
        }
        col = f"prediction_{period}"
        now = datetime.now().isoformat()
        self.conn.execute(
            f"UPDATE signal_records SET {col} = ?, updated_at = ? WHERE signal_id = ?",
            [json.dumps(pred, ensure_ascii=False), now, signal_id],
        )

    def record_outcome(
        self,
        signal_id: str,
        period: str,
        actual_price: float,
        actual_score: int = None,
        actual_grade: str = None,
        actual_signal: str = None,
        actual_revenue: float = None,
        actual_ni: float = None,
    ) -> None:
        """记录实际结果。period='6m' or '12m'。"""
        outcome = {
            "actual_price": actual_price,
            "actual_score": actual_score,
            "actual_grade": actual_grade,
            "actual_signal": actual_signal,
            "actual_revenue": actual_revenue,
            "actual_ni": actual_ni,
        }
        col = f"actual_{period}"
        now = datetime.now().isoformat()

        # 更新状态
        new_status = "active_12m" if period == "6m" else "completed"
        self.conn.execute(
            f"UPDATE signal_records SET {col} = ?, status = ?, updated_at = ? WHERE signal_id = ?",
            [json.dumps(outcome, ensure_ascii=False), new_status, now, signal_id],
        )

    def generate_review(self, signal_id: str) -> dict:
        """比较预测与实际，计算准确度，生成经验教训。"""
        row = self.conn.execute(
            "SELECT * FROM signal_records WHERE signal_id = ?", [signal_id]
        ).fetchone()
        if not row:
            return {"error": f"未找到信号: {signal_id}"}

        cols = [d[0] for d in self.conn.execute("SELECT * FROM signal_records LIMIT 0").description]
        rec = dict(zip(cols, row))

        results = {}
        for period in ("6m", "12m"):
            pred = json.loads(rec[f"prediction_{period}"]) if rec[f"prediction_{period}"] else {}
            actual = json.loads(rec[f"actual_{period}"]) if rec[f"actual_{period}"] else {}
            if not pred or not actual:
                continue

            expected_price = pred.get("expected_price", 0)
            actual_price = actual.get("actual_price", 0)

            # 价格准确度
            if expected_price > 0:
                price_acc = max(0, 1 - abs(actual_price - expected_price) / expected_price)
            else:
                price_acc = 0

            # 评分准确度
            expected_score = pred.get("expected_score", 0)
            actual_score = actual.get("actual_score", expected_score)
            score_acc = max(0, 1 - abs(actual_score - expected_score) / 40)

            # 方向准确度
            pred_direction = 1 if expected_price > (rec.get("company_state") and json.loads(rec["company_state"]).get("price", 0) or 0) else -1
            baseline_price = json.loads(rec["company_state"]).get("price", 0) if rec["company_state"] else 0
            actual_direction = 1 if actual_price > baseline_price else -1
            direction_acc = 1.0 if pred_direction == actual_direction else 0.0

            results[period] = {
                "price_accuracy": round(price_acc, 4),
                "score_accuracy": round(score_acc, 4),
                "direction_accuracy": direction_acc,
                "expected_price": expected_price,
                "actual_price": actual_price,
                "expected_score": expected_score,
                "actual_score": actual_score,
            }

        # 生成经验教训
        avg_acc = 0
        if results:
            avg_acc = sum(
                (r["price_accuracy"] + r["score_accuracy"]) / 2 for r in results.values()
            ) / len(results)

        if avg_acc > 0.8:
            lessons = "分析框架有效，继续保持"
            improvement = "维持当前评分体系和决策标准"
        elif avg_acc > 0.5:
            # 找最弱维度
            dims = json.loads(rec["dimension_scores"]) if rec["dimension_scores"] else {}
            weakest = min(dims, key=dims.get) if dims else "未知"
            lessons = f"部分准确，需要改进{weakest}"
            improvement = f"重点优化{weakest}维度的评分逻辑"
        else:
            lessons = "预测偏差大，需要重新审视基本面分析因素"
            improvement = "考虑引入更多外部数据源，重新校准评分权重"

        now = datetime.now().isoformat()
        self.conn.execute(
            """UPDATE signal_records SET
                prediction_accuracy = ?, lessons_learned = ?,
                system_improvement = ?, updated_at = ?
            WHERE signal_id = ?""",
            [
                json.dumps(results, ensure_ascii=False),
                lessons,
                improvement,
                now,
                signal_id,
            ],
        )

        return {
            "signal_id": signal_id,
            "accuracy": results,
            "lessons_learned": lessons,
            "system_improvement": improvement,
            "avg_accuracy": round(avg_acc, 4),
        }

    def get_pending_reviews(self, period: str = "6m") -> list:
        """获取需要回顾的信号（已过6m/12m但未记录结果）。"""
        if period == "6m":
            status_filter = "active_6m"
        else:
            status_filter = "active_12m"

        rows = self.conn.execute(
            """SELECT signal_id, ticker, company_name, signal_date, signal_type,
                      total_score, grade, status
               FROM signal_records WHERE status = ?
               ORDER BY signal_date""",
            [status_filter],
        ).fetchall()

        results = []
        for row in rows:
            results.append({
                "signal_id": row[0],
                "ticker": row[1],
                "company_name": row[2],
                "signal_date": str(row[3]) if row[3] else "",
                "signal_type": row[4],
                "total_score": row[5],
                "grade": row[6],
                "status": row[7],
            })
        return results

    def get_signal_history(self, ticker: str = None) -> list:
        """获取所有信号记录，可按 ticker 过滤。"""
        if ticker:
            rows = self.conn.execute(
                "SELECT * FROM signal_records WHERE ticker = ? ORDER BY signal_date",
                [ticker],
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM signal_records ORDER BY signal_date"
            ).fetchall()

        cols = [d[0] for d in self.conn.execute("SELECT * FROM signal_records LIMIT 0").description]
        return [dict(zip(cols, row)) for row in rows]

    def get_accuracy_stats(self) -> dict:
        """汇总所有已完成信号的预测准确度。"""
        rows = self.conn.execute(
            """SELECT prediction_accuracy, prediction_6m, prediction_12m
               FROM signal_records
               WHERE prediction_accuracy IS NOT NULL AND prediction_accuracy != 'null'"""
        ).fetchall()

        if not rows:
            return {
                "price_accuracy": 0,
                "score_accuracy": 0,
                "direction_accuracy": 0,
                "total_signals": 0,
                "avg_confidence": 0,
            }

        total = len(rows)
        price_accs = []
        score_accs = []
        dir_accs = []
        confidences = []

        for row in rows:
            acc = json.loads(row[0]) if row[0] else {}
            for period_data in acc.values():
                price_accs.append(period_data.get("price_accuracy", 0))
                score_accs.append(period_data.get("score_accuracy", 0))
                dir_accs.append(period_data.get("direction_accuracy", 0))

            for pred_col in (row[1], row[2]):
                if pred_col:
                    pred = json.loads(pred_col)
                    confidences.append(pred.get("confidence", 0))

        return {
            "price_accuracy": round(sum(price_accs) / max(len(price_accs), 1), 4),
            "score_accuracy": round(sum(score_accs) / max(len(score_accs), 1), 4),
            "direction_accuracy": round(sum(dir_accs) / max(len(dir_accs), 1), 4),
            "total_signals": total,
            "avg_confidence": round(sum(confidences) / max(len(confidences), 1), 2),
        }

    def generate_signal_report(self, signal_id: str) -> str:
        """为一条信号生成完整的 Markdown 报告。"""
        row = self.conn.execute(
            "SELECT * FROM signal_records WHERE signal_id = ?", [signal_id]
        ).fetchone()
        if not row:
            return f"未找到信号: {signal_id}"

        cols = [d[0] for d in self.conn.execute("SELECT * FROM signal_records LIMIT 0").description]
        rec = dict(zip(cols, row))

        cs = json.loads(rec["company_state"]) if rec["company_state"] else {}
        dims = json.loads(rec["dimension_scores"]) if rec["dimension_scores"] else {}
        details = json.loads(rec["analysis_details"]) if rec["analysis_details"] else {}
        pred6 = json.loads(rec["prediction_6m"]) if rec["prediction_6m"] else {}
        pred12 = json.loads(rec["prediction_12m"]) if rec["prediction_12m"] else {}
        act6 = json.loads(rec["actual_6m"]) if rec["actual_6m"] else {}
        act12 = json.loads(rec["actual_12m"]) if rec["actual_12m"] else {}
        acc = json.loads(rec["prediction_accuracy"]) if rec["prediction_accuracy"] else {}

        lines = [
            f"# 信号报告: {rec['signal_id']}",
            "",
            "## 1. 基本信息",
            f"- 股票代码: {rec['ticker']}",
            f"- 公司名称: {rec['company_name']}",
            f"- 信号日期: {rec['signal_date']}",
            f"- 信号类型: {rec['signal_type']}",
            f"- 信号来源: {rec['signal_source']}",
            f"- 状态: {rec['status']}",
            "",
            "## 2. 公司状态快照",
        ]
        for k, v in cs.items():
            lines.append(f"- {k}: {v}")

        lines += ["", "## 3. 七维评分"]
        for k, v in dims.items():
            lines.append(f"- {k}: {v}")
        lines.append(f"- 总分: {rec['total_score']}  等级: {rec['grade']}")

        if details:
            lines += ["", "## 4. 分析详情"]
            for dim, detail in details.items():
                lines.append(f"### {dim}")
                if isinstance(detail, dict):
                    for dk, dv in detail.items():
                        lines.append(f"- {dk}: {dv}")
                else:
                    lines.append(f"- {detail}")

        lines += ["", "## 5. 用户行动"]
        lines.append(f"- 行动: {rec['user_action'] or '未记录'}")
        if rec["user_shares"]:
            lines.append(f"- 股数: {rec['user_shares']}, 价格: {rec['user_price']}")
        if rec["user_reason"]:
            lines.append(f"- 原因: {rec['user_reason']}")

        lines += ["", "## 6. 预测"]
        for label, pred in [("6个月", pred6), ("12个月", pred12)]:
            if pred:
                lines.append(f"### {label}预测")
                lines.append(f"- 预期价格: {pred.get('expected_price')}")
                lines.append(f"- 预期评分: {pred.get('expected_score')}, 等级: {pred.get('expected_grade')}")
                lines.append(f"- 置信度: {pred.get('confidence')}/5")
                lines.append(f"- 理由: {pred.get('reasoning')}")

        lines += ["", "## 7. 实际结果"]
        for label, act in [("6个月", act6), ("12个月", act12)]:
            if act:
                lines.append(f"### {label}实际")
                lines.append(f"- 实际价格: {act.get('actual_price')}")
                lines.append(f"- 实际评分: {act.get('actual_score')}, 等级: {act.get('actual_grade')}")

        if acc:
            lines += ["", "## 8. 预测准确度"]
            for period, data in acc.items():
                lines.append(f"### {period}")
                lines.append(f"- 价格准确度: {data.get('price_accuracy', 0):.1%}")
                lines.append(f"- 评分准确度: {data.get('score_accuracy', 0):.1%}")
                lines.append(f"- 方向准确度: {'✓' if data.get('direction_accuracy') else '✗'}")

        if rec["lessons_learned"]:
            lines += ["", "## 9. 经验教训", rec["lessons_learned"]]
        if rec["system_improvement"]:
            lines += ["", "## 10. 系统改进建议", rec["system_improvement"]]

        return "\n".join(lines)

    def generate_tracker_summary(self) -> str:
        """生成所有信号的概览报告。"""
        rows = self.conn.execute(
            """SELECT signal_id, ticker, company_name, signal_date, signal_type,
                      total_score, grade, status, user_action
               FROM signal_records ORDER BY signal_date DESC"""
        ).fetchall()

        if not rows:
            return "# 信号追踪概览\n\n暂无信号记录。"

        status_counts = {}
        for r in rows:
            s = r[7]
            status_counts[s] = status_counts.get(s, 0) + 1

        lines = ["# 信号追踪概览", ""]
        lines.append("## 状态统计")
        for s, c in status_counts.items():
            label = {"pending": "待处理", "active_6m": "等待6月回顾", "active_12m": "等待12月回顾", "completed": "已完成"}.get(s, s)
            lines.append(f"- {label}: {c}条")
        lines.append(f"- 总计: {len(rows)}条")
        lines.append("")
        lines.append("## 最近信号")
        lines.append("| 信号ID | 股票 | 名称 | 日期 | 类型 | 评分 | 等级 | 状态 | 行动 |")
        lines.append("|--------|------|------|------|------|------|------|------|------|")
        for r in rows:
            status_label = {"pending": "待处理", "active_6m": "6月等待", "active_12m": "12月等待", "completed": "已完成"}.get(r[7], r[7])
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {status_label} | {r[8] or '-'} |")

        return "\n".join(lines)
