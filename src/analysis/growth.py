"""Growth analysis module.

Checks:
  1. revenue growth rate > 0 (latest period)
  2. trend: non-declining across periods
  3. growth quality: no one-time drivers (only if data provided)
  4. 5-year revenue CAGR
  5. 5-year average ROE + trend stability
  6. 5-year average gross margin + trend stability

ROE/Gross Margin stability:
  - Trend: is it growing, stable, or declining across years?
  - Volatility: range > 20pp (ROE) or > 15pp (毛利率) → volatile → penalty
  - Growing + low volatility → bonus
  - Declining or volatile → penalty

Scoring:
  5: consistent positive growth, accelerating trend, strong CAGR
  4: positive growth but decelerating, or moderate CAGR
  3: no growth data available (neutral)
  2: negative growth or 1 issue
  1: multiple issues (declining + negative)
"""


def _cagr(rates: list[float]) -> float | None:
    """Compute CAGR from a list of YoY growth rates.

    E.g. rates = [0.10, 0.20, 0.15] means 3 years of growth.
    CAGR = ((1+r1) * (1+r2) * ... * (1+rn))^(1/n) - 1
    """
    if not rates:
        return None
    cumulative = 1.0
    for r in rates:
        cumulative *= (1 + r)
    n = len(rates)
    if cumulative <= 0:
        return None
    return cumulative ** (1.0 / n) - 1


def _assess_stability(rates: list[float], label: str,
                      high_range: float = 0.20) -> dict:
    """Assess trend direction and volatility for a multi-year metric.

    Args:
        rates: list of yearly values (e.g. [0.15, 0.18, 0.20, 0.17, 0.19])
        label: metric name for details (e.g. "ROE", "毛利率")
        high_range: threshold for range to be considered volatile (default 20pp)

    Returns:
        dict with:
            'avg' — average value
            'trend' — 'growing' | 'stable' | 'declining'
            'volatility' — 'low' | 'high'
            'penalty' — int (-1, 0)
            'bonus' — int (0, 1)
            'details' — list of str
    """
    n = len(rates)
    if n == 0:
        return {"avg": 0, "trend": "stable", "volatility": "low", "penalty": 0, "bonus": 0, "details": []}
    avg = sum(rates) / n
    r_min = min(rates)
    r_max = max(rates)
    r_range = r_max - r_min

    result = {"avg": avg, "trend": "stable", "volatility": "low",
              "penalty": 0, "bonus": 0, "details": []}

    # Trend: compare first half avg vs second half avg
    if n >= 3:
        mid = n // 2
        first_half = sum(rates[:mid]) / mid
        second_half = sum(rates[mid:]) / (n - mid)
        diff = second_half - first_half
        if diff > 0.03:  # > 3pp improvement
            result["trend"] = "growing"
        elif diff < -0.03:  # > 3pp decline
            result["trend"] = "declining"
        else:
            result["trend"] = "stable"
    elif n == 2:
        diff = rates[1] - rates[0]
        if diff > 0.03:
            result["trend"] = "growing"
        elif diff < -0.03:
            result["trend"] = "declining"

    # Volatility: range check
    if r_range > high_range:
        result["volatility"] = "high"

    # Trend labels
    trend_cn = {"growing": "上升", "stable": "稳定", "declining": "下降"}
    vol_cn = {"low": "稳定", "high": "波动大"}

    # Build detail string
    result["details"].append(
        f"5yr {label}: avg={avg:.1%}, range=[{r_min:.1%}, {r_max:.1%}], "
        f"趋势={trend_cn[result['trend']]}, 波动={vol_cn[result['volatility']]}"
    )

    # Scoring adjustments
    if result["trend"] == "declining":
        result["penalty"] = 1
        result["details"].append(f"  ⚠ {label}呈下降趋势 - penalty 1")
    elif result["volatility"] == "high":
        result["penalty"] = 1
        result["details"].append(f"  ⚠ {label}波动过大(range={r_range:.1%}) - penalty 1")
    elif result["trend"] == "growing" and result["volatility"] == "low":
        result["bonus"] = 1
        result["details"].append(f"  ✓ {label}稳步上升 + low volatility - bonus 1")

    return result


def _sustainable_growth(roe: float | None, payout_ratio: float | None) -> float | None:
    """Sustainable growth rate = ROE × (1 - payout ratio).

    This is the maximum growth a company can sustain using only retained
    earnings.  If actual growth exceeds this, the company relies on
    external financing (debt or equity issuance).

    Args:
        roe: return on equity (e.g. 0.15 for 15%)
        payout_ratio: dividend payout ratio (e.g. 0.30 for 30%)

    Returns:
        sustainable growth rate, or None if inputs are missing.
    """
    if roe is None or payout_ratio is None:
        return None
    return roe * (1 - payout_ratio)


def score(data: dict) -> dict:
    """Score growth based on revenue growth trends and long-term averages.

    Args:
        data: dict with keys:
            'revenue_growth_rates' (list of float) — YoY or QoQ rates
            'growth_type' (str, optional) — 'yoy' (default) or 'qoq'
            'growth_drivers' (list of str, optional)
            'roe_rates' (list of float, optional) — multi-year ROE
            'gross_margin_rates' (list of float, optional) — multi-year gross margins
            'latest_roe' (float, optional) — most recent ROE
            'payout_ratio' (float, optional) — dividend payout ratio

    Returns:
        dict with 'score' (int 0-5) and 'details' (list of str)
    """
    details = []
    growth_rates = data.get("revenue_growth_rates", [])
    growth_type = data.get("growth_type", "yoy")
    drivers = data.get("growth_drivers", [])
    roe_rates = data.get("roe_rates", [])
    gm_rates = data.get("gross_margin_rates", [])

    # QoQ → annualized conversion
    if growth_type == "qoq" and growth_rates:
        # QoQ转年化: (1+qoq)^4 - 1
        annualized = [(1 + r) ** 4 - 1 for r in growth_rates]
        details.append(
            f"QoQ data detected, annualized: "
            f"{[f'{r:.1%}' for r in annualized[:3]]}..."
        )
        growth_rates = annualized

    if not growth_rates:
        details.append("growth: no multi-period data available - score 3 (neutral)")
        return {"score": 3, "details": details}

    # Check 1: latest growth rate
    latest_rate = growth_rates[-1]
    if latest_rate > 0.10:
        details.append(f"latest growth: {latest_rate:.1%} > 10% - strong")
        growth_quality = "strong"
    elif latest_rate > 0:
        details.append(f"latest growth: {latest_rate:.1%} in (0, 10%] - moderate")
        growth_quality = "moderate"
    else:
        details.append(f"latest growth: {latest_rate:.1%} <= 0 - declining")
        growth_quality = "negative"

    # Check 2: trend across periods
    if len(growth_rates) >= 2:
        declining_periods = sum(
            1 for i in range(1, len(growth_rates))
            if growth_rates[i] < growth_rates[i - 1]
        )
        total_transitions = len(growth_rates) - 1
        decline_ratio = declining_periods / total_transitions

        avg_rate = sum(growth_rates) / len(growth_rates)
        rate_range = max(growth_rates) - min(growth_rates)

        if decline_ratio == 0:
            details.append(f"trend: consistently non-declining ({len(growth_rates)} periods) - strong")
            trend_quality = "strong"
        elif decline_ratio <= 0.5 and avg_rate > 0:
            details.append(f"trend: mixed but net positive (avg {avg_rate:.1%}) - moderate")
            trend_quality = "moderate"
        else:
            details.append(f"trend: mostly declining ({declining_periods}/{total_transitions} transitions) - weak")
            trend_quality = "weak"

        # Volatility penalty
        if rate_range > 0.5:
            details.append(f"volatility: range {rate_range:.1%} is high - penalize 1")
            volatility_penalty = 1
        else:
            volatility_penalty = 0
    else:
        details.append("trend: only 1 period, trend check N/A")
        trend_quality = "single"
        volatility_penalty = 0

    # Check 3: one-time drivers (only if provided)
    if drivers:
        onetime_keywords = ["one-time", "one time", "一次性", "非经常", "偶尔", "偶发"]
        onetime_found = any(
            any(kw in d.lower() for kw in onetime_keywords) for d in drivers
        )
        if onetime_found:
            details.append(f"growth drivers: one-time factors detected - penalize 1")
            onetime_penalty = 1
        else:
            onetime_penalty = 0
    else:
        onetime_penalty = 0

    # Check 4: 5-year revenue CAGR
    cagr = _cagr(growth_rates)
    if cagr is not None:
        years = len(growth_rates)
        if cagr > 0.15:
            details.append(f"5yr CAGR: {cagr:.1%} ({years}yr) > 15% - excellent")
            cagr_quality = "excellent"
        elif cagr > 0.08:
            details.append(f"5yr CAGR: {cagr:.1%} ({years}yr) in (8%, 15%] - good")
            cagr_quality = "good"
        elif cagr > 0:
            details.append(f"5yr CAGR: {cagr:.1%} ({years}yr) in (0, 8%] - moderate")
            cagr_quality = "moderate"
        else:
            details.append(f"5yr CAGR: {cagr:.1%} ({years}yr) <= 0 - declining")
            cagr_quality = "declining"
    else:
        details.append("5yr CAGR: insufficient data - SKIP")
        cagr_quality = "skip"

    # Check 5: 5-year average ROE + stability
    roe_stability = _assess_stability(roe_rates, "ROE", high_range=0.20)
    if roe_rates and len(roe_rates) >= 2:
        avg_roe = roe_stability["avg"]
        if avg_roe > 0.15:
            details.append(f"5yr avg ROE: {avg_roe:.1%} ({len(roe_rates)}yr) > 15% - excellent")
            roe_quality = "excellent"
        elif avg_roe > 0.10:
            details.append(f"5yr avg ROE: {avg_roe:.1%} ({len(roe_rates)}yr) in (10%, 15%] - good")
            roe_quality = "good"
        elif avg_roe > 0:
            details.append(f"5yr avg ROE: {avg_roe:.1%} ({len(roe_rates)}yr) in (0, 10%] - moderate")
            roe_quality = "moderate"
        else:
            details.append(f"5yr avg ROE: {avg_roe:.1%} ({len(roe_rates)}yr) <= 0 - poor")
            roe_quality = "poor"
        details.extend(roe_stability["details"])
    else:
        details.append("5yr avg ROE: insufficient data - SKIP")
        roe_quality = "skip"

    # Check 6: 5-year average gross margin + stability
    gm_stability = _assess_stability(gm_rates, "毛利率", high_range=0.15)
    if gm_rates and len(gm_rates) >= 2:
        avg_gm = gm_stability["avg"]
        if avg_gm > 0.40:
            details.append(f"5yr avg 毛利率: {avg_gm:.1%} ({len(gm_rates)}yr) > 40% - excellent")
            gm_quality = "excellent"
        elif avg_gm > 0.25:
            details.append(f"5yr avg 毛利率: {avg_gm:.1%} ({len(gm_rates)}yr) in (25%, 40%] - good")
            gm_quality = "good"
        elif avg_gm > 0.15:
            details.append(f"5yr avg 毛利率: {avg_gm:.1%} ({len(gm_rates)}yr) in (15%, 25%] - moderate")
            gm_quality = "moderate"
        else:
            details.append(f"5yr avg 毛利率: {avg_gm:.1%} ({len(gm_rates)}yr) <= 15% - poor")
            gm_quality = "poor"
        details.extend(gm_stability["details"])
    else:
        details.append("5yr avg 毛利率: insufficient data - SKIP")
        gm_quality = "skip"

    # Check 7: sustainable growth rate cross-validation
    roe_latest = data.get("latest_roe")
    payout = data.get("payout_ratio")
    sust_growth = _sustainable_growth(roe_latest, payout)
    if sust_growth is not None and latest_rate > 0:
        if latest_rate > sust_growth * 1.5:
            details.append(
                f"sustainable_growth: 实际{latest_rate:.1%} > "
                f"可持续{sust_growth:.1%}×1.5 (依赖外部融资) - WARN"
            )
            # Warning only — does not affect score
        elif latest_rate <= sust_growth:
            details.append(
                f"sustainable_growth: 实际{latest_rate:.1%} <= "
                f"可持续{sust_growth:.1%} (内生增长) - PASS"
            )

    # Determine final score
    base_score = {
        ("strong", "strong"): 5,
        ("strong", "moderate"): 5,
        ("strong", "single"): 5,
        ("moderate", "strong"): 5,
        ("moderate", "moderate"): 4,
        ("moderate", "weak"): 3,
        ("moderate", "single"): 4,
        ("negative", "strong"): 3,
        ("negative", "moderate"): 2,
        ("negative", "weak"): 1,
        ("negative", "single"): 2,
    }.get((growth_quality, trend_quality), 3)

    # CAGR bonus/penalty (±1)
    cagr_adj = 0
    if cagr_quality == "excellent":
        cagr_adj = 1
        details.append(f"CAGR bonus: +1 (excellent 5yr CAGR)")
    elif cagr_quality == "declining":
        cagr_adj = -1
        details.append(f"CAGR penalty: -1 (declining 5yr CAGR)")

    # ROE/GM stability adjustments (±1 each)
    stability_adj = roe_stability.get("penalty", 0) + roe_stability.get("bonus", 0) \
                  + gm_stability.get("penalty", 0) + gm_stability.get("bonus", 0)
    if stability_adj != 0:
        details.append(f"stability_adj: {stability_adj:+d} (ROE: {roe_stability.get('penalty',0)+roe_stability.get('bonus',0):+d}, 毛利率: {gm_stability.get('penalty',0)+gm_stability.get('bonus',0):+d})")

    final_score = max(0, min(5, base_score - volatility_penalty - onetime_penalty + cagr_adj + stability_adj))
    details.append(f"final: base={base_score} - volatility={volatility_penalty} - onetime={onetime_penalty} + cagr={cagr_adj} + stability={stability_adj} = {final_score}")

    return {"score": final_score, "details": details}
