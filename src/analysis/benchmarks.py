"""Industry benchmarks and relative scoring module (W3.1).

Provides sector-level median financial metrics and a function to compare
a company's metrics against its industry benchmark, yielding
percentile-like scores.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Industry benchmark data
# Keyed by sector slug.  Values are *medians* sourced from public A-share /
# US-listed sector studies (representative mid-2020s figures).
# ---------------------------------------------------------------------------

INDUSTRY_BENCHMARKS: dict[str, dict] = {
    "technology": {
        "median_gross_margin": 0.45,
        "median_net_margin": 0.12,
        "median_roe": 0.14,
        "median_debt_ratio": 0.35,
        "median_revenue_growth": 0.15,
        "typical_pe_range": (25, 60),
    },
    "consumer": {
        "median_gross_margin": 0.35,
        "median_net_margin": 0.08,
        "median_roe": 0.12,
        "median_debt_ratio": 0.45,
        "median_revenue_growth": 0.10,
        "typical_pe_range": (18, 40),
    },
    "auto_parts": {
        "median_gross_margin": 0.22,
        "median_net_margin": 0.06,
        "median_roe": 0.10,
        "median_debt_ratio": 0.50,
        "median_revenue_growth": 0.08,
        "typical_pe_range": (12, 30),
    },
    "internet": {
        "median_gross_margin": 0.55,
        "median_net_margin": 0.15,
        "median_roe": 0.18,
        "median_debt_ratio": 0.30,
        "median_revenue_growth": 0.20,
        "typical_pe_range": (30, 80),
    },
    "healthcare": {
        "median_gross_margin": 0.55,
        "median_net_margin": 0.10,
        "median_roe": 0.12,
        "median_debt_ratio": 0.35,
        "median_revenue_growth": 0.12,
        "typical_pe_range": (25, 55),
    },
    "finance": {
        "median_gross_margin": 0.40,
        "median_net_margin": 0.25,
        "median_roe": 0.10,
        "median_debt_ratio": 0.85,
        "median_revenue_growth": 0.06,
        "typical_pe_range": (8, 20),
    },
    "manufacturing": {
        "median_gross_margin": 0.20,
        "median_net_margin": 0.05,
        "median_roe": 0.09,
        "median_debt_ratio": 0.55,
        "median_revenue_growth": 0.05,
        "typical_pe_range": (10, 25),
    },
    "energy": {
        "median_gross_margin": 0.25,
        "median_net_margin": 0.07,
        "median_roe": 0.08,
        "median_debt_ratio": 0.50,
        "median_revenue_growth": 0.04,
        "typical_pe_range": (8, 18),
    },
    "materials": {
        "median_gross_margin": 0.18,
        "median_net_margin": 0.05,
        "median_roe": 0.08,
        "median_debt_ratio": 0.50,
        "median_revenue_growth": 0.04,
        "typical_pe_range": (8, 20),
    },
    "real_estate": {
        "median_gross_margin": 0.25,
        "median_net_margin": 0.08,
        "median_roe": 0.10,
        "median_debt_ratio": 0.70,
        "median_revenue_growth": 0.05,
        "typical_pe_range": (6, 15),
    },
}

# Sensible default benchmark used when a sector is not found.
_DEFAULT_BENCHMARK = {
    "median_gross_margin": 0.25,
    "median_net_margin": 0.08,
    "median_roe": 0.10,
    "median_debt_ratio": 0.50,
    "median_revenue_growth": 0.08,
    "typical_pe_range": (15, 35),
}


def get_benchmark(sector: str) -> dict:
    """Return the industry benchmark dict for *sector*.

    Falls back to a sensible default when the sector is unknown.
    """
    key = sector.strip().lower().replace(" ", "_").replace("-", "_")
    return INDUSTRY_BENCHMARKS.get(key, _DEFAULT_BENCHMARK)


def _percentile_like(value: float, median: float, higher_is_better: bool = True) -> float:
    """Return a 0-100 percentile-like score for *value* relative to *median*.

    Uses a simple ratio approach clamped to [0, 100]:
      - If the metric is "higher is better" (margin, ROE, growth), score = (value / median) * 50
        clamped to [0, 100].
      - If the metric is "lower is better" (debt_ratio), inverted.
    """
    if median == 0:
        return 50.0  # can't compare, neutral

    if higher_is_better:
        raw = (value / median) * 50.0
    else:
        # lower is better → invert
        raw = (median / value) * 50.0 if value > 0 else 100.0

    return max(0.0, min(100.0, raw))


def relative_score(industry_name: str, metrics: dict) -> dict:
    """Compare a company's *metrics* against the benchmark for *industry_name*.

    Parameters
    ----------
    industry_name : str
        Sector key (e.g. "technology", "auto_parts").
    metrics : dict
        Company metrics. Recognised keys:
        gross_margin, net_margin, roe, debt_ratio, revenue_growth, pe_ratio.

    Returns
    -------
    dict with:
        - "benchmark": the benchmark dict used
        - "scores": dict of per-metric percentile-like scores (0-100)
        - "overall": average of available scores
    """
    bench = get_benchmark(industry_name)

    score_map: dict[str, float] = {}

    metric_bench_pairs = [
        ("gross_margin",    "median_gross_margin",    True),
        ("net_margin",      "median_net_margin",      True),
        ("roe",             "median_roe",              True),
        ("debt_ratio",      "median_debt_ratio",       False),
        ("revenue_growth",  "median_revenue_growth",   True),
    ]

    for metric_key, bench_key, higher_better in metric_bench_pairs:
        val = metrics.get(metric_key)
        if val is not None:
            score_map[metric_key] = _percentile_like(val, bench[bench_key], higher_better)

    # PE scoring: closer to lower end of typical range is better
    pe = metrics.get("pe_ratio")
    if pe is not None:
        lo, hi = bench["typical_pe_range"]
        if pe <= lo:
            score_map["pe_ratio"] = 100.0
        elif pe >= hi:
            score_map["pe_ratio"] = 0.0
        else:
            # Linear interpolation: lower PE → higher score
            score_map["pe_ratio"] = max(0.0, min(100.0, (hi - pe) / (hi - lo) * 100.0))

    overall = sum(score_map.values()) / len(score_map) if score_map else 50.0

    return {
        "benchmark": bench,
        "scores": score_map,
        "overall": round(overall, 1),
    }
