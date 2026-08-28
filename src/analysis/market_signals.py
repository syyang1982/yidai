"""Market signal alerts module (W1.2).

Three signal types:
  1. Announcement Sentiment – keyword-based sentiment scoring
  2. Industry Health – metric-driven industry expansion/contraction scoring
  3. Management Change Detection – keyword scan for leadership changes
"""

import re

# ---------------------------------------------------------------------------
# 1. Announcement Sentiment
# ---------------------------------------------------------------------------

NEGATIVE_KEYWORDS: list[str] = [
    "下调", "承压", "不确定", "风险", "下降", "亏损", "违约", "处罚",
    "诉讼", "裁员", "暴雷", "暴跌", "清仓", "减持", "退市", "警告",
    "罚款", "立案", "违规", "跌停",
]

POSITIVE_KEYWORDS: list[str] = [
    "增长", "突破", "创新", "超预期", "扩张", "合作", "利好", "涨停",
    "增持", "回购", "分红", "盈利", "订单", "签约", "中标",
]


def score_announcement_sentiment(text: str) -> dict:
    """Score sentiment of an announcement text.

    Scans *text* for pre-defined negative and positive Chinese keywords
    and returns a sentiment assessment.

    Returns:
        dict with keys:
            sentiment     – 'negative' / 'neutral' / 'positive'
            negative_count – number of negative keyword hits
            positive_count – number of positive keyword hits
            keywords_found – list of matched keywords (deduplicated)
            score          – int 0-5 (5 = very positive, 1 = very negative)
    """
    if not text or not text.strip():
        return {
            "sentiment": "neutral",
            "negative_count": 0,
            "positive_count": 0,
            "keywords_found": [],
            "score": 3,
        }

    found_negative: list[str] = []
    found_positive: list[str] = []

    for kw in NEGATIVE_KEYWORDS:
        if kw in text:
            found_negative.append(kw)

    for kw in POSITIVE_KEYWORDS:
        if kw in text:
            found_positive.append(kw)

    neg = len(found_negative)
    pos = len(found_positive)
    total = neg + pos
    keywords_found = list(dict.fromkeys(found_negative + found_positive))  # deduplicated, order preserved

    if total == 0:
        return {
            "sentiment": "neutral",
            "negative_count": 0,
            "positive_count": 0,
            "keywords_found": [],
            "score": 3,
        }

    # Score: map net-sentiment ratio to 0-5
    # pos_ratio = pos / total  (0.0 = all negative, 1.0 = all positive)
    # score = round(pos_ratio * 4) + 1  → maps [0,1] to [1,5]
    pos_ratio = pos / total
    raw_score = pos_ratio * 4 + 1
    score = max(1, min(5, round(raw_score)))

    if score >= 4:
        sentiment = "positive"
    elif score <= 2:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "negative_count": neg,
        "positive_count": pos,
        "keywords_found": keywords_found,
        "score": score,
    }


# ---------------------------------------------------------------------------
# 2. Industry Health
# ---------------------------------------------------------------------------

# Default thresholds per industry.  Any industry not listed falls back to
# the "default" entry.
_INDUSTRY_THRESHOLDS: dict[str, dict] = {
    "default": {
        "pmi": {"expanding": 50.5, "contracting": 49.5},
        "sales_growth": {"expanding": 10.0, "contracting": 0.0},
        "inventory_ratio": {"expanding": 1.2, "contracting": 1.8},  # lower is better
        "capacity_utilization": {"expanding": 80.0, "contracting": 70.0},
    },
    "半导体": {
        "pmi": {"expanding": 51.0, "contracting": 49.0},
        "sales_growth": {"expanding": 15.0, "contracting": 0.0},
        "inventory_ratio": {"expanding": 1.1, "contracting": 1.7},
        "capacity_utilization": {"expanding": 85.0, "contracting": 72.0},
    },
    "新能源": {
        "pmi": {"expanding": 51.0, "contracting": 49.0},
        "sales_growth": {"expanding": 20.0, "contracting": 5.0},
        "inventory_ratio": {"expanding": 1.1, "contracting": 1.6},
        "capacity_utilization": {"expanding": 82.0, "contracting": 70.0},
    },
    "消费": {
        "pmi": {"expanding": 50.5, "contracting": 49.5},
        "sales_growth": {"expanding": 8.0, "contracting": -2.0},
        "inventory_ratio": {"expanding": 1.3, "contracting": 1.9},
        "capacity_utilization": {"expanding": 78.0, "contracting": 68.0},
    },
}


def _get_thresholds(industry: str) -> dict:
    return _INDUSTRY_THRESHOLDS.get(industry, _INDUSTRY_THRESHOLDS["default"])


def _score_single_metric(metric: str, value: float, thresholds: dict) -> tuple[int, str]:
    """Return (points, detail_str) for a single metric.

    points: 2 = expanding, 1 = stable, 0 = contracting
    """
    th = thresholds.get(metric)
    if th is None:
        return 1, f"{metric}: {value} — 无阈值数据，按中性处理"

    exp = th["expanding"]
    con = th["contracting"]

    # For inventory_ratio, *lower* is better → invert comparison
    if metric == "inventory_ratio":
        if value <= exp:
            return 2, f"{metric}: {value} ≤ {exp} — 景气"
        elif value >= con:
            return 0, f"{metric}: {value} ≥ {con} — 收缩"
        else:
            return 1, f"{metric}: {value} — 稳定"
    else:
        if value >= exp:
            return 2, f"{metric}: {value} ≥ {exp} — 景气"
        elif value <= con:
            return 0, f"{metric}: {value} ≤ {con} — 收缩"
        else:
            return 1, f"{metric}: {value} — 稳定"


def score_industry_health(industry: str, metrics: dict) -> dict:
    """Score industry health based on macro metrics.

    Args:
        industry: industry name (e.g. '半导体', '新能源', '消费')
        metrics: dict with optional keys pmi, sales_growth,
                 inventory_ratio, capacity_utilization

    Returns:
        dict with 'score' (0-5), 'status' ('expanding'/'stable'/'contracting'),
        and 'details' (list of str).
    """
    thresholds = _get_thresholds(industry)

    if not metrics:
        return {"score": 3, "status": "stable", "details": ["无数据，默认中性评分"]}

    details: list[str] = []
    total_points = 0
    scored_count = 0

    for metric_name in ("pmi", "sales_growth", "inventory_ratio", "capacity_utilization"):
        value = metrics.get(metric_name)
        if value is None:
            details.append(f"{metric_name}: 缺失 — 跳过")
            continue
        points, detail = _score_single_metric(metric_name, value, thresholds)
        total_points += points
        scored_count += 1
        details.append(detail)

    if scored_count == 0:
        return {"score": 3, "status": "stable", "details": details + ["无有效指标，默认中性评分"]}

    # average points (0-2) → scale to 0-5
    avg = total_points / scored_count  # 0.0 – 2.0
    # Map: 0→0, 0.5→1, 1.0→2/3, 1.5→4, 2.0→5
    score = max(0, min(5, round(avg * 2.5)))

    if score >= 4:
        status = "expanding"
    elif score <= 1:
        status = "contracting"
    else:
        status = "stable"

    return {"score": score, "status": status, "details": details}


# ---------------------------------------------------------------------------
# 3. Management Change Detection
# ---------------------------------------------------------------------------

MGMT_KEYWORDS: list[str] = [
    "辞职", "离任", "变更", "新任", "解聘", "免职", "卸任",
    "聘任", "接任", "代理", "调任", "退休",
]

# Severity: higher = more significant change
_SEVERITY_MAP: dict[str, str] = {
    "辞职": "high",
    "离任": "high",
    "解聘": "high",
    "免职": "high",
    "退休": "medium",
    "卸任": "medium",
    "变更": "medium",
    "调任": "medium",
    "新任": "medium",
    "聘任": "medium",
    "接任": "medium",
    "代理": "low",
}


def detect_management_change(announcements: list[str]) -> list[dict]:
    """Scan a list of announcement texts for management change signals.

    Args:
        announcements: list of announcement text strings

    Returns:
        list of dicts, each with:
            text     – the original announcement text
            keyword  – matched keyword
            severity – 'high' / 'medium' / 'low'
    """
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (text_hash, keyword) dedup

    for text in announcements:
        if not text:
            continue
        for kw in MGMT_KEYWORDS:
            if kw in text:
                key = (text, kw)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "text": text,
                        "keyword": kw,
                        "severity": _SEVERITY_MAP.get(kw, "low"),
                    })
    return results
