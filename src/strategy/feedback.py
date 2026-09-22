"""闭环反馈层 — 把复盘结论回灌到评分权重/阈值。

闭环链路（本模块补上第 ④ 环）::

    ① 分析   src/analysis/scorer.py + src/data/models.py     → 评分 + 信号
    ② 记录   src/strategy/decision.py + position.py          → 决策日志 + 持仓
    ③ 复盘   src/strategy/review_engine.py + accuracy_audit  → 维度预测力 / 认知偏差
    ④ 反馈   本模块                                          → 权重回灌 ①

设计原则（防过拟合优先）：

- **样本量门槛** ``MIN_SAMPLES``：高分组+低分组样本不足的维度一律维持基准权重，
  不参与调权。审计显示 90 天窗口下多维度只有 3 条样本，据此调权必然过拟合。
- **调权幅度受限** ``WEIGHT_CLAMP``：单维权重只能在 [0.3, 2.0] 之间，
  且每次相对基准的倍率只在 0.7x ~ 1.25x 四档内跳，不允许连续微调。
- **总量守恒**：调权后 renormalize 使 ``sum(weights) == 8.2``（基准总量）。
  这样 ``_compute_weighted_total`` 的满分仍是 41.0，BUY 门槛 33 的语义不变，
  不会出现"换了权重导致所有信号漂移"的隐性破坏。
- **默认 dry-run**：写入覆盖文件需要显式 ``--apply``，随时 ``--reset`` 撤回。

覆盖文件 ``config/feedback_weights.json`` 由 :func:`apply_feedback` 生成，
:func:`src.data.models.load_dimension_weights` 读取。文件缺失/损坏时静默回退默认值。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.data.models import (
    DIMENSION_WEIGHTS,
    FEEDBACK_WEIGHTS_FILE,
    load_dimension_weights,
    reset_dimension_weights_cache,
)

# ── 调参常量 ──────────────────────────────────────────────────────────
#: 高分组+低分组样本数低于此值的维度不参与调权
MIN_SAMPLES = 30
#: 单维权重硬边界
WEIGHT_CLAMP = (0.3, 2.0)
#: 基准权重总量（renormalize 目标，保持满分 41.0 / BUY 门槛 33 的语义）
TARGET_WEIGHT_SUM = sum(DIMENSION_WEIGHTS.values())

# 有效性(effectiveness，单位=高分组收益-低分组收益的百分点) → 权重倍率
# 四档跳变，刻意不做连续映射，避免噪声被放大
_STEP_TABLE: List[Tuple[float, float]] = [
    (+5.0, 1.25),   # 强预测力 → 显著加权
    ( +0.0, 1.10),  # 弱正预测力 → 轻微加权
    (-5.0, 0.90),   # 弱负预测力 → 轻微降权
]
#: 反预测力（<= -5pp）→ 显著降权
_REVERSE_MULTIPLIER = 0.70

# 维度名统一到 models.DIMENSION_WEIGHTS 的英文键
DIM_ALIASES: Dict[str, str] = {
    "盈利": "profitability", "profitability": "profitability", "profit": "profitability",
    "健康": "health", "health": "health",
    "现金流": "cashflow", "cashflow": "cashflow", "cash_flow": "cashflow",
    "估值": "valuation", "valuation": "valuation",
    "成长": "growth", "growth": "growth",
    "股息": "dividend", "dividend": "dividend", "dividend_quality": "dividend",
    "股东": "ownership", "ownership": "ownership",
    "战略": "strategy", "strategy": "strategy",
}


@dataclass
class DimFeedback:
    """单个维度的回灌建议。"""
    dimension: str
    base_weight: float
    proposed_weight: float
    effectiveness: float = 0.0          # 高分组收益 - 低分组收益（百分点）
    samples: int = 0                    # 高分组 + 低分组样本数
    actioned: bool = False              # 是否参与了本次调权
    reason: str = ""

    @property
    def changed(self) -> bool:
        return abs(self.proposed_weight - self.base_weight) > 1e-9


@dataclass
class FeedbackReport:
    """一次回灌计算的完整结果。"""
    generated_at: str = ""
    dims: List[DimFeedback] = field(default_factory=list)
    total_samples: int = 0
    applied: bool = False
    applied_path: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def actionable(self) -> bool:
        return any(d.actioned for d in self.dims)

    @property
    def changed_dims(self) -> List[DimFeedback]:
        return [d for d in self.dims if d.changed]


# ── 名称归一 ──────────────────────────────────────────────────────────
def canonical_dim(name: Optional[str]) -> Optional[str]:
    """把维度名归一成 models.DIMENSION_WEIGHTS 的英文键；未知返回 None。"""
    if not name:
        return None
    key = str(name).strip().lower()
    return DIM_ALIASES.get(key) or DIM_ALIASES.get(str(name).strip())


# ── 核心：从预测力推导权重 ────────────────────────────────────────────
def _multiplier_for(effectiveness: float) -> float:
    """把有效性(百分点)映射成权重倍率，四档跳变。"""
    for threshold, mult in _STEP_TABLE:
        if effectiveness > threshold:
            return mult
    return _REVERSE_MULTIPLIER


def derive_weights(
    effectiveness: Dict[str, Tuple[float, int]],
    base: Optional[Dict[str, float]] = None,
) -> List[DimFeedback]:
    """由维度预测力推导新权重。

    Parameters
    ----------
    effectiveness:
        ``{维度名: (effectiveness百分点, 样本数)}``，维度名可中可英。
    base:
        基准权重，默认 :data:`DIMENSION_WEIGHTS`。

    Returns
    -------
    List[DimFeedback]
        每个维度的调权建议，已按 ``sum == TARGET_WEIGHT_SUM`` 归一（仅对参与调权的维度）。
    """
    base = dict(base or DIMENSION_WEIGHTS)
    raw: Dict[str, float] = dict(base)
    infos: Dict[str, DimFeedback] = {}

    for dim in DIMENSION_WEIGHTS:
        infos[dim] = DimFeedback(
            dimension=dim,
            base_weight=base[dim],
            proposed_weight=base[dim],
            reason="维持基准权重",
        )

    for name, (eff, n) in (effectiveness or {}).items():
        dim = canonical_dim(name)
        if dim is None:
            continue
        info = infos[dim]
        info.effectiveness = float(eff)
        info.samples = int(n)
        if int(n) < MIN_SAMPLES:
            info.reason = f"样本不足({int(n)}<{MIN_SAMPLES})，不参与调权"
            continue
        mult = _multiplier_for(float(eff))
        clamped = min(max(base[dim] * mult, WEIGHT_CLAMP[0]), WEIGHT_CLAMP[1])
        raw[dim] = clamped
        info.actioned = True
        info.reason = f"有效性{float(eff):+.1f}pp / 样本{int(n)} → {mult}x"

    # 只对参与调权的维度做总量守恒缩放，其余维度保持基准值不动
    actioned_dims = [d for d in DIMENSION_WEIGHTS if infos[d].actioned]
    if actioned_dims:
        actioned_sum = sum(raw[d] for d in actioned_dims)
        rest_sum = sum(base[d] for d in DIMENSION_WEIGHTS if d not in actioned_dims)
        target_actioned = TARGET_WEIGHT_SUM - rest_sum
        if actioned_sum > 0 and target_actioned > 0:
            scale = target_actioned / actioned_sum
            for d in actioned_dims:
                scaled = min(max(raw[d] * scale, WEIGHT_CLAMP[0]), WEIGHT_CLAMP[1])
                infos[d].proposed_weight = round(scaled, 3)

    return [infos[d] for d in DIMENSION_WEIGHTS]


# ── 复盘数据来源 ──────────────────────────────────────────────────────
def collect_effectiveness_from_reviews(
    db_path: Optional[str] = None,
) -> Tuple[Dict[str, Tuple[float, int]], int, List[str]]:
    """从 review_engine 的 review_results 表收集维度预测力。

    Returns
    -------
    (effectiveness映射, 总样本数, warnings)
    """
    warnings: List[str] = []
    try:
        from src.strategy.review_engine import ReviewEngine
    except Exception as e:  # pragma: no cover - import guard
        return {}, 0, [f"无法导入 ReviewEngine: {e}"]

    if db_path is None:
        try:
            from src.strategy.position import default_decision_db
            db_path = default_decision_db()
        except Exception:
            db_path = None

    engine = None
    try:
        engine = ReviewEngine(db_path=db_path) if db_path else ReviewEngine()
        stats = engine.analyze_dimension_effectiveness()
    except Exception as e:
        return {}, 0, [f"读取 review_results 失败: {e}"]
    finally:
        try:
            if engine is not None:
                engine.conn.close()
        except Exception:
            pass

    if not stats:
        return {}, 0, ["review_results 为空或样本不足 —— 复盘环节尚无产出"]

    out: Dict[str, Tuple[float, int]] = {}
    total = 0
    for e in stats:
        dim = canonical_dim(e.dimension)
        if dim is None:
            warnings.append(f"未知维度名 {e.dimension!r}，已跳过")
            continue
        n = int(e.high_score_count) + int(e.low_score_count)
        out[dim] = (float(e.effectiveness), n)
        total += n
    return out, total, warnings


def collect_effectiveness_from_audit() -> Tuple[Dict[str, Tuple[float, int]], int, List[str]]:
    """备用来源：从 accuracy_audit 的维度预测力报告收集（口径略有差异）。"""
    try:
        from src.analysis.accuracy_audit import AccuracyAuditor
    except Exception as e:  # pragma: no cover
        return {}, 0, [f"无法导入 AccuracyAuditor: {e}"]
    try:
        aud = AccuracyAuditor()
        result = aud.generate_full_report()
    except Exception as e:
        return {}, 0, [f"accuracy_audit 读取失败: {e}"]

    dims = (result or {}).get("dimension_predictivity") or []
    if not dims:
        return {}, 0, ["accuracy_audit 无维度预测力数据"]
    out: Dict[str, Tuple[float, int]] = {}
    total = 0
    for item in dims:
        if not isinstance(item, dict):
            continue
        dim = canonical_dim(item.get("dimension") or item.get("dim") or item.get("name"))
        if dim is None:
            continue
        eff = float(item.get("predictivity") or item.get("effectiveness") or 0.0)
        n = int(item.get("samples") or item.get("n") or item.get("count") or 0)
        # accuracy_audit 的 predictivity 是 -1..1 的相关系数，放大到百分点量级
        out[dim] = (eff * 100.0, n)
        total += n
    return out, total, ["来源: accuracy_audit(口径与 review_results 不同，仅供参考)"]


# ── 顶层流程 ──────────────────────────────────────────────────────────
def build_report(db_path: Optional[str] = None) -> FeedbackReport:
    """计算回灌建议（dry-run，不写文件）。"""
    report = FeedbackReport(generated_at=datetime.now().isoformat(timespec="seconds"))

    eff, total, warns = collect_effectiveness_from_reviews(db_path)
    if not eff:
        eff2, total2, warns2 = collect_effectiveness_from_audit()
        report.warnings.extend(warns)
        report.warnings.extend(warns2)
        if eff2:
            eff, total = eff2, total2
    else:
        report.warnings.extend(warns)

    report.total_samples = total
    report.dims = derive_weights(eff)

    cur = load_dimension_weights()
    if any(abs(cur[k] - DIMENSION_WEIGHTS[k]) > 1e-9 for k in DIMENSION_WEIGHTS):
        report.warnings.append(
            "当前生效权重已偏离内置基准（存在 feedback_weights.json 覆盖），"
            "本次建议是基于内置基准重新推导"
        )
    return report


def apply_feedback(report: FeedbackReport, write: bool = True) -> Optional[str]:
    """把建议写入 config/feedback_weights.json（write=False 时只标记不落盘）。"""
    if not report.actionable:
        report.warnings.append("无任何维度达到样本门槛，拒绝写入（避免用噪声过拟合权重）")
        return None
    payload = {
        "generated_at": report.generated_at,
        "source": "review_engine.dimension_effectiveness",
        "min_samples": MIN_SAMPLES,
        "target_weight_sum": round(TARGET_WEIGHT_SUM, 3),
        "weights": {d.dimension: d.proposed_weight for d in report.dims},
        "detail": [
            {
                "dimension": d.dimension,
                "effectiveness_pp": round(d.effectiveness, 2),
                "samples": d.samples,
                "base": d.base_weight,
                "proposed": d.proposed_weight,
                "reason": d.reason,
            }
            for d in report.dims
        ],
    }
    if not write:
        return None
    os.makedirs(os.path.dirname(FEEDBACK_WEIGHTS_FILE), exist_ok=True)
    with open(FEEDBACK_WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    reset_dimension_weights_cache()
    report.applied = True
    report.applied_path = FEEDBACK_WEIGHTS_FILE
    return FEEDBACK_WEIGHTS_FILE


def reset_feedback() -> bool:
    """删除覆盖文件，恢复内置默认权重。"""
    try:
        if os.path.exists(FEEDBACK_WEIGHTS_FILE):
            os.remove(FEEDBACK_WEIGHTS_FILE)
        reset_dimension_weights_cache()
        return True
    except OSError:
        return False


def format_report(report: FeedbackReport) -> str:
    """终端可读的回灌报告（纯文本，CJK 已按双宽对齐）。"""
    from src.ops.text_table import row as _row, rule as _rule  # 延迟导入避免循环

    L: List[str] = []
    L.append("=" * 74)
    L.append("  意怠工程 — 闭环反馈 ④ 复盘 → 评分权重")
    L.append("=" * 74)
    L.append("")
    L.append(f"  生成时间: {report.generated_at}")
    L.append(f"  复盘样本: {report.total_samples} 条  (调权门槛 {MIN_SAMPLES} 条/维)")
    L.append("")

    L.append(_row(["维度", "基准权重", "建议权重", "变化", "有效性", "样本", "结论"]))
    L.append(_rule([6, 10, 10, 10, 10, 8, 24]))
    for d in report.dims:
        delta = d.proposed_weight - d.base_weight
        delta_s = f"{delta:+.2f}" if abs(delta) > 1e-9 else "—"
        verdict = d.reason if d.actioned else ("样本不足" if d.samples else "无数据")
        L.append(_row([
            d.dimension,
            f"{d.base_weight:.2f}",
            f"{d.proposed_weight:.2f}",
            delta_s,
            f"{d.effectiveness:+.1f}pp" if d.samples else "—",
            str(d.samples) if d.samples else "—",
            verdict,
        ]))
    L.append("")

    if report.changed_dims:
        L.append(f"  建议变更: {len(report.changed_dims)} 个维度")
    else:
        L.append("  建议变更: 无（权重维持基准）")

    for w in report.warnings:
        L.append(f"  ⚠️  {w}")

    L.append("")
    if report.applied:
        L.append(f"  ✅ 已写入: {report.applied_path}")
        L.append("     评分层即刻生效；`manage.py feedback --reset` 可撤回。")
    elif not report.actionable:
        L.append("  ⛔ 未写入 —— 没有维度达到样本门槛。先跑 `manage.py review run` 累积复盘样本。")
    else:
        L.append("  💡 dry-run。确认无误后加 --apply 写入；--reset 恢复默认权重。")
    L.append("")
    return "\n".join(L)
