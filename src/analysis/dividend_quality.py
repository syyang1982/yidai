"""分红质量评分模块。

核心逻辑：
  1. 股息率越高越好（股息/股价）
  2. 同等股息率下，分红率越低越好（分红率=股息/净利润）
     因为低分红率意味着公司有更大空间提升分红
  3. 股息增长趋势加分

示例：
  中国神华：股息率5%，分红率100% → 已到天花板
  招商银行：股息率5%，分红率35%  → 还有65%提升空间

  两家股息率相同，但招商银行的分红质量得分更高。

评分维度（总分5分）：
  - 股息率绝对水平 (0-3分)
  - 分红率空间奖励 (0-1分) — 分红率<50%且股息率>0时加分
  - 股息增长趋势 (0-1分) — 近3年股息持续增长加分

输入数据：
  data = {
      "dividend_yield": 0.05,        # 股息率 (5%)
      "payout_ratio": 0.35,          # 分红率 (35%)
      "dividend_growth_rates": [0.10, 0.15, 0.20],  # 近3年每股股息增长率
      "has_dividend": True,          # 是否有分红
  }
"""

from __future__ import annotations


def score(data: dict) -> dict:
    """评分分红质量。

    Args:
        data: dict with keys:
            - dividend_yield (float): 股息率, 如0.05表示5%
            - payout_ratio (float): 分红率, 如0.35表示35%
            - dividend_growth_rates (list[float]): 近N年每股股息增长率
            - has_dividend (bool): 是否有分红

    Returns:
        dict with 'score' (int 0-5) and 'details' (list of str)
    """
    details = []
    has_dividend = data.get("has_dividend", False)

    if not has_dividend:
        details.append("分红质量: 无分红 — score 0")
        return {"score": 0, "details": details}

    dy = data.get("dividend_yield", 0) or 0
    pr = data.get("payout_ratio")  # 可能为None
    growth_rates = data.get("dividend_growth_rates", [])

    # ── 1. 股息率绝对水平 (0-3分) ──
    # 1%以下=0, 1-2%=1, 2-3%=2, 3%以上=3
    if dy >= 0.03:
        dy_score = 3
        details.append(f"股息率: {dy:.2%} ≥ 3% — 优秀 (+3)")
    elif dy >= 0.02:
        dy_score = 2
        details.append(f"股息率: {dy:.2%} in [2%, 3%) — 良好 (+2)")
    elif dy >= 0.01:
        dy_score = 1
        details.append(f"股息率: {dy:.2%} in [1%, 2%) — 一般 (+1)")
    else:
        dy_score = 0
        details.append(f"股息率: {dy:.2%} < 1% — 偏低 (+0)")

    # ── 2. 分红率空间奖励 (0-1分) ──
    # 核心逻辑：分红率越低，提升空间越大
    # 分红率<50%且有分红 → +1
    # 分红率<30%且股息率>2% → 额外说明（极具提升潜力）
    pr_bonus = 0
    if pr is not None and pr >= 0:
        if pr < 0.50 and dy > 0:
            pr_bonus = 1
            headroom = (0.50 - pr) / pr * 100  # 假设50%为合理上限
            details.append(
                f"分红率: {pr:.1%} < 50% — 提升空间大 (+1) "
                f"[若提至50%，股息率可达 {dy * 0.50 / pr:.2%}]"
            )
        elif pr >= 0.80:
            details.append(
                f"分红率: {pr:.1%} ≥ 80% — 已近天花板 (+0) "
                f"[提升空间极小]"
            )
        else:
            details.append(f"分红率: {pr:.1%} — 中等 (+0)")
    else:
        details.append("分红率: 数据缺失 — 跳过空间评估")

    # ── 3. 股息增长趋势 (0-1分) ──
    growth_bonus = 0
    if growth_rates and len(growth_rates) >= 2:
        # 所有年份都增长 → +1
        all_positive = all(r > 0 for r in growth_rates)
        avg_growth = sum(growth_rates) / len(growth_rates)

        if all_positive and avg_growth > 0.05:
            growth_bonus = 1
            details.append(
                f"股息增长: 连续{len(growth_rates)}年增长, "
                f"平均{avg_growth:.1%} — 趋势良好 (+1)"
            )
        elif all_positive:
            details.append(
                f"股息增长: 连续{len(growth_rates)}年增长, "
                f"平均{avg_growth:.1%} — 增长较慢 (+0)"
            )
        else:
            declining = sum(1 for r in growth_rates if r < 0)
            details.append(
                f"股息增长: {declining}/{len(growth_rates)}年下降 — 趋势不佳 (+0)"
            )
    else:
        details.append("股息增长: 数据不足 — 跳过趋势评估")

    # ── 总分 ──
    final_score = dy_score + pr_bonus + growth_bonus
    final_score = min(5, max(0, final_score))
    details.append(f"分红质量总分: {dy_score} + {pr_bonus} + {growth_bonus} = {final_score}/5")

    return {"score": final_score, "details": details}


def compute_dividend_metrics(
    dividend_per_share: float,
    stock_price: float,
    net_income_per_share: float,
    historical_dps: list[float] | None = None,
) -> dict:
    """计算分红相关指标，供评分使用。

    Args:
        dividend_per_share: 每股股息（年度）
        stock_price: 当前股价
        net_income_per_share: 每股收益
        historical_dps: 历年每股股息列表（从旧到新）

    Returns:
        dict ready for score()
    """
    has_dividend = dividend_per_share > 0

    dy = dividend_per_share / stock_price if stock_price > 0 else 0
    pr = dividend_per_share / net_income_per_share if net_income_per_share > 0 else None

    growth_rates = []
    if historical_dps and len(historical_dps) >= 2:
        for i in range(1, len(historical_dps)):
            prev = historical_dps[i - 1]
            curr = historical_dps[i]
            if prev > 0:
                growth_rates.append((curr - prev) / prev)

    return {
        "dividend_yield": dy,
        "payout_ratio": pr,
        "dividend_growth_rates": growth_rates,
        "has_dividend": has_dividend,
    }
