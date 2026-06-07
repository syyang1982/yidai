"""
财务异常检测 — 意怠工程 (Yidai)

规则型预警，在基本面恶化影响价格之前发出信号。
每条规则返回 AnomalyAlert，包含严重等级：
  🔴 HIGH   — 建议减仓
  🟡 MEDIUM — 标记跟踪
  🟢 LOW    — 信息性，无需动作

设计原则：
- 所有字段都是 Optional，数据缺失时跳过该规则（不报错）
- 需要至少 2 期数据才能做趋势判断
- 与 scorer.py 并行运行，不修改评分逻辑
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AnomalyAlert:
    """一条异常预警。"""
    rule_id: str            # e.g. "W1.1.1"
    rule_name: str          # e.g. "应收账款 vs 营收增速"
    severity: str           # "HIGH" / "MEDIUM" / "LOW"
    emoji: str              # "🔴" / "🟡" / "🟢"
    ticker: str
    company_name: str = ""
    period: str = ""        # 触发时的报告期
    detail: str = ""        # 人类可读的说明
    metrics: dict = field(default_factory=dict)  # 关键数值


def detect_anomalies(
    ticker: str,
    annual_data: list[dict],
    company_name: str = "",
) -> List[AnomalyAlert]:
    """对一家公司多年财报运行全部异常检测规则。

    Args:
        ticker: 股票代码
        annual_data: 按时间升序排列的年度财报数据列表
        company_name: 公司名称（用于报告）

    Returns:
        按严重程度排序的预警列表
    """
    if len(annual_data) < 2:
        return []

    alerts: List[AnomalyAlert] = []
    alerts.extend(_check_ar_vs_revenue(ticker, annual_data, company_name))
    alerts.extend(_check_inventory_turnover(ticker, annual_data, company_name))
    alerts.extend(_check_profit_quality(ticker, annual_data, company_name))
    alerts.extend(_check_short_loan_long_invest(ticker, annual_data, company_name))
    alerts.extend(_check_goodwill_ratio(ticker, annual_data, company_name))

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda a: severity_order.get(a.severity, 9))
    return alerts


# ---------------------------------------------------------------------------
# Rule W1.1.1: 应收账款增速 vs 营收增速
# 连续 2 期应收增速 > 营收增速 + 10% → 🔴
# ---------------------------------------------------------------------------
def _check_ar_vs_revenue(
    ticker: str, data: list[dict], company_name: str,
) -> List[AnomalyAlert]:
    """检测应收账款增速持续超过营收增速。"""
    alerts = []
    consecutive = 0
    trigger_period = ""

    for i in range(1, len(data)):
        curr = data[i]
        prev = data[i - 1]

        ar_curr = curr.get("accounts_receivable")
        ar_prev = prev.get("accounts_receivable")
        rev_curr = curr.get("revenue")
        rev_prev = prev.get("revenue")

        if None in (ar_curr, ar_prev, rev_curr, rev_prev):
            continue
        if ar_prev == 0 or rev_prev == 0:
            continue

        ar_growth = (ar_curr - ar_prev) / ar_prev
        rev_growth = (rev_curr - rev_prev) / rev_prev

        if ar_growth > rev_growth + 0.10:
            consecutive += 1
            trigger_period = curr.get("period", "")
        else:
            consecutive = 0

    if consecutive >= 2:
        alerts.append(AnomalyAlert(
            rule_id="W1.1.1",
            rule_name="应收账款 vs 营收增速",
            severity="HIGH",
            emoji="🔴",
            ticker=ticker,
            company_name=company_name,
            period=trigger_period,
            detail=f"连续{consecutive}期应收账款增速超过营收增速10%以上，可能存在放水冲收入或回款恶化",
            metrics={"consecutive_periods": consecutive},
        ))
    elif consecutive == 1:
        alerts.append(AnomalyAlert(
            rule_id="W1.1.1",
            rule_name="应收账款 vs 营收增速",
            severity="MEDIUM",
            emoji="🟡",
            ticker=ticker,
            company_name=company_name,
            period=trigger_period,
            detail="最近一期应收账款增速超过营收增速10%以上，需持续关注",
            metrics={"consecutive_periods": 1},
        ))

    return alerts


# ---------------------------------------------------------------------------
# Rule W1.1.2: 存货周转率趋势
# 连续 3 期下降 → 🟡
# ---------------------------------------------------------------------------
def _check_inventory_turnover(
    ticker: str, data: list[dict], company_name: str,
) -> List[AnomalyAlert]:
    """检测存货周转率持续下降。"""
    # 计算每期存货周转率 = 营收 / 存货
    turnover_rates = []
    periods = []
    for d in data:
        inv = d.get("inventory")
        rev = d.get("revenue")
        if inv is not None and rev is not None and inv > 0:
            turnover_rates.append(rev / inv)
            periods.append(d.get("period", ""))

    if len(turnover_rates) < 3:
        return []

    # 检查最近 N 期是否连续下降
    declining_count = 0
    for i in range(len(turnover_rates) - 1, 0, -1):
        if turnover_rates[i] < turnover_rates[i - 1]:
            declining_count += 1
        else:
            break

    if declining_count >= 3:
        return [AnomalyAlert(
            rule_id="W1.1.2",
            rule_name="存货周转率趋势",
            severity="MEDIUM",
            emoji="🟡",
            ticker=ticker,
            company_name=company_name,
            period=periods[-1],
            detail=f"存货周转率连续{declining_count}期下降，产品可能滞销，未来可能计提减值",
            metrics={
                "declining_periods": declining_count,
                "latest_turnover": round(turnover_rates[-1], 2),
                "peak_turnover": round(max(turnover_rates), 2),
            },
        )]
    return []


# ---------------------------------------------------------------------------
# Rule W1.1.3: 利润质量
# 经营现金流 < 净利润（连续 2 期）→ 🟡
# ---------------------------------------------------------------------------
def _check_profit_quality(
    ticker: str, data: list[dict], company_name: str,
) -> List[AnomalyAlert]:
    """检测利润质量：经营现金流是否支撑净利润。"""
    consecutive = 0
    trigger_period = ""

    for d in data:
        ocf = d.get("operating_cash_flow")
        ni = d.get("net_income")

        if None in (ocf, ni):
            continue
        if ni <= 0:
            # 亏损公司不适用此规则
            consecutive = 0
            continue

        if ocf < ni:
            consecutive += 1
            trigger_period = d.get("period", "")
        else:
            consecutive = 0

    if consecutive >= 2:
        return [AnomalyAlert(
            rule_id="W1.1.3",
            rule_name="利润质量",
            severity="MEDIUM",
            emoji="🟡",
            ticker=ticker,
            company_name=company_name,
            period=trigger_period,
            detail=f"连续{consecutive}期经营现金流低于净利润，利润质量差，可能有会计操纵",
            metrics={"consecutive_periods": consecutive},
        )]
    return []


# ---------------------------------------------------------------------------
# Rule W1.1.4: 短贷长投
# 短期借款激增 + 长期投资增加 → 🔴
# ---------------------------------------------------------------------------
def _check_short_loan_long_invest(
    ticker: str, data: list[dict], company_name: str,
) -> List[AnomalyAlert]:
    """检测短贷长投风险。"""
    if len(data) < 2:
        return []

    latest = data[-1]
    prev = data[-2]

    sl_curr = latest.get("short_loan")
    sl_prev = prev.get("short_loan")
    lti_curr = latest.get("long_term_invest")
    lti_prev = prev.get("long_term_invest")
    ta = latest.get("total_assets")

    if None in (sl_curr, sl_prev, lti_curr, lti_prev, ta) or ta == 0:
        return []

    # 短期借款激增：增幅 > 30% 且占总资产 > 5%
    sl_growth = (sl_curr - sl_prev) / sl_prev if sl_prev > 0 else (1.0 if sl_curr > 0 else 0)
    sl_ratio = sl_curr / ta

    # 长期投资增加
    lti_growth = (lti_curr - lti_prev) / lti_prev if lti_prev > 0 else (1.0 if lti_curr > 0 else 0)

    if sl_growth > 0.30 and sl_ratio > 0.05 and lti_growth > 0.10:
        return [AnomalyAlert(
            rule_id="W1.1.4",
            rule_name="短贷长投",
            severity="HIGH",
            emoji="🔴",
            ticker=ticker,
            company_name=company_name,
            period=latest.get("period", ""),
            detail=f"短期借款增长{sl_growth*100:.0f}%（占总资产{sl_ratio*100:.1f}%），同时长期投资增长{lti_growth*100:.0f}%，流动性风险加大",
            metrics={
                "short_loan_growth": round(sl_growth * 100, 1),
                "short_loan_ratio": round(sl_ratio * 100, 1),
                "lti_growth": round(lti_growth * 100, 1),
            },
        )]
    return []


# ---------------------------------------------------------------------------
# Rule W1.1.5: 商誉占比
# 商誉/总资产比例上升超 5% → 🟡
# ---------------------------------------------------------------------------
def _check_goodwill_ratio(
    ticker: str, data: list[dict], company_name: str,
) -> List[AnomalyAlert]:
    """检测商誉占比异常。"""
    ratios = []
    periods = []
    for d in data:
        gw = d.get("goodwill")
        ta = d.get("total_assets")
        if gw is not None and ta is not None and ta > 0:
            ratios.append(gw / ta)
            periods.append(d.get("period", ""))

    if len(ratios) < 2:
        return []

    latest_ratio = ratios[-1]
    prev_ratio = ratios[-2]
    delta = latest_ratio - prev_ratio

    # 当前商誉占比 > 10% 且上升 > 5 个百分点
    if latest_ratio > 0.10 and delta > 0.05:
        return [AnomalyAlert(
            rule_id="W1.1.5",
            rule_name="商誉占比",
            severity="MEDIUM",
            emoji="🟡",
            ticker=ticker,
            company_name=company_name,
            period=periods[-1],
            detail=f"商誉占总资产{latest_ratio*100:.1f}%（上升{delta*100:.1f}个百分点），靠并购撑业绩，未来减值风险大",
            metrics={
                "goodwill_ratio": round(latest_ratio * 100, 1),
                "ratio_change": round(delta * 100, 1),
            },
        )]
    elif latest_ratio > 0.20:
        return [AnomalyAlert(
            rule_id="W1.1.5",
            rule_name="商誉占比",
            severity="MEDIUM",
            emoji="🟡",
            ticker=ticker,
            company_name=company_name,
            period=periods[-1],
            detail=f"商誉占总资产{latest_ratio*100:.1f}%，商誉过高，减值风险显著",
            metrics={"goodwill_ratio": round(latest_ratio * 100, 1)},
        )]
    return []


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def format_alerts(alerts: List[AnomalyAlert], company_name: str = "") -> str:
    """将预警列表格式化为 Markdown。"""
    if not alerts:
        name = company_name or "该公司"
        return f"  🟢 {name}：未检测到异常信号\n"

    lines = []
    name = alerts[0].company_name or company_name or alerts[0].ticker
    lines.append(f"### {name} 异常预警\n")

    for a in alerts:
        lines.append(f"{a.emoji} **[{a.rule_id}] {a.rule_name}** ({a.severity})")
        lines.append(f"  - {a.detail}")
        if a.period:
            lines.append(f"  - 报告期: {a.period}")
        if a.metrics:
            kv = ", ".join(f"{k}={v}" for k, v in a.metrics.items())
            lines.append(f"  - 指标: {kv}")
        lines.append("")

    return "\n".join(lines)
