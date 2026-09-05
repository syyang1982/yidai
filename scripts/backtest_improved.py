#!/usr/bin/env python3
"""改进后回测 — 验证三项改进效果。"""
import json
from collections import defaultdict

with open("/home/frank/.hermes/yidai/reports/historical_prices.json") as f:
    all_data = json.load(f)

# Company-level configs
company_configs = {
    "1810.HK": {"buy_threshold": 5, "pe_cap": 0.85, "reduce_days": 90},
    "2252.HK": {"buy_threshold": 5, "pe_cap": 0.85, "reduce_days": 90},
    "9896.HK": {"buy_threshold": 8, "pe_cap": 0.60, "reduce_days": 120},
    "002352.SZ": {"buy_threshold": 8, "pe_cap": 0.60, "reduce_days": 90},
    "600933.SS": {"buy_threshold": 7, "pe_cap": 0.65, "reduce_days": 90},
    "2020.HK": {"buy_threshold": 7, "pe_cap": 0.70, "reduce_days": 90},
    "3888.HK": {"buy_threshold": 7, "pe_cap": 0.70, "reduce_days": 90},
    "1361.HK": {"buy_threshold": 7, "pe_cap": 0.70, "reduce_days": 90},
    "LX": {"buy_threshold": 7, "pe_cap": 0.65, "reduce_days": 120},
}
default_cfg = {"buy_threshold": 5, "pe_cap": 0.80, "reduce_days": 90}


def compute_momentum(prices, idx, months):
    if idx < months:
        return None
    p0 = prices[idx - months]["close"]
    p1 = prices[idx]["close"]
    return (p1 - p0) / p0 if p0 > 0 else None


def compute_ma(prices, idx, months):
    if idx < months - 1:
        return None
    window = [prices[i]["close"] for i in range(idx - months + 1, idx + 1)]
    return sum(window) / len(window)


def compute_pe_percentile(prices, idx, window=24):
    """Proxy: current price position in N-month range."""
    if idx < window:
        return None
    recent = [prices[i]["close"] for i in range(idx - window + 1, idx + 1)]
    current = prices[idx]["close"]
    below = sum(1 for p in recent if p < current)
    return below / len(recent)


def generate_signal_improved(prices, idx, ticker, prev_signals):
    m3 = compute_momentum(prices, idx, 3)
    m6 = compute_momentum(prices, idx, 6)
    m12 = compute_momentum(prices, idx, 12)
    ma6 = compute_ma(prices, idx, 6)
    ma12 = compute_ma(prices, idx, 12)
    pe_pct = compute_pe_percentile(prices, idx)
    price = prices[idx]["close"]

    cfg = company_configs.get(ticker, default_cfg)

    if any(v is None for v in [m3, m6]):
        return "HOLD", "insufficient_data"

    # REDUCE (unchanged)
    if m12 is not None and m12 < -0.30:
        return "REDUCE", f"12m={m12:.1%}"
    if m6 < -0.25 and m3 < -0.15:
        return "REDUCE", f"6m={m6:.1%},3m={m3:.1%}"
    if ma12 is not None and price < ma12 and m6 < -0.20:
        return "REDUCE", "below_12m_MA"

    # BUY score
    buy_score = 0
    if m6 > 0:
        buy_score += 1
    if m12 is not None and m12 > -0.10:
        buy_score += 1
    if ma6 is not None and price > ma6:
        buy_score += 1
    if m3 > -0.15:
        buy_score += 1
    if m6 > 0.15:
        buy_score += 1
    if m3 > 0.05:
        buy_score += 1

    if buy_score >= cfg["buy_threshold"]:
        # Improvement 1: PE percentile guard
        if pe_pct is not None and pe_pct > cfg["pe_cap"]:
            return "HOLD", f"val_guard:pe_pct={pe_pct:.0%}"

        # Improvement 2: REDUCE holding protection
        last_reduce = prev_signals.get("last_reduce_idx")
        if last_reduce is not None:
            months_since = idx - last_reduce
            if months_since * 30 < cfg["reduce_days"]:
                return "HOLD", f"reduce_protect:{months_since}m"

        return "BUY", f"score={buy_score}"

    return "HOLD", f"score={buy_score}"


# Baseline (original rules)
def generate_signal_baseline(prices, idx):
    m3 = compute_momentum(prices, idx, 3)
    m6 = compute_momentum(prices, idx, 6)
    m12 = compute_momentum(prices, idx, 12)
    ma6 = compute_ma(prices, idx, 6)

    if any(v is None for v in [m3, m6]):
        return "HOLD"

    if m12 is not None and m12 < -0.30:
        return "REDUCE"
    if m6 < -0.25 and m3 < -0.15:
        return "REDUCE"

    buy_score = 0
    if m6 > 0:
        buy_score += 1
    if m12 is not None and m12 > -0.10:
        buy_score += 1
    if ma6 is not None and prices[idx]["close"] > ma6:
        buy_score += 1
    if m3 > -0.15:
        buy_score += 1
    if m6 > 0.15:
        buy_score += 1
    if m3 > 0.05:
        buy_score += 1

    if buy_score >= 5:
        return "BUY"
    return "HOLD"


# ============================================================
# Run BOTH backtests
# ============================================================
baseline_results = []
improved_results = []

for ticker, info in all_data.items():
    name = info["name"]
    prices = info["prices"]
    prev_signals = {}

    for idx in range(len(prices)):
        dt = prices[idx]["date"]
        if dt < "2024-01":
            continue

        p0 = prices[idx]["close"]

        # Baseline
        sig_b = generate_signal_baseline(prices, idx)

        # Improved
        sig_i, reason_i = generate_signal_improved(prices, idx, ticker, prev_signals)
        if sig_i == "REDUCE":
            prev_signals["last_reduce_idx"] = idx

        forward = {}
        for months in [3, 6, 9, 12]:
            future_idx = idx + months
            if future_idx < len(prices):
                pf = prices[future_idx]["close"]
                ret = (pf - p0) / p0
                forward[f"T+{months}m"] = {"return": round(ret, 4)}

        baseline_results.append({"ticker": ticker, "name": name, "signal": sig_b, "forward": forward})
        improved_results.append({"ticker": ticker, "name": name, "signal": sig_i, "forward": forward})


def analyze(results, label):
    by_sig = defaultdict(list)
    for r in results:
        by_sig[r["signal"]].append(r)

    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"  Signals: BUY={len(by_sig['BUY'])}, HOLD={len(by_sig['HOLD'])}, REDUCE={len(by_sig['REDUCE'])}")
    print(f"{'=' * 70}")

    for sig in ["BUY", "REDUCE"]:
        records = by_sig[sig]
        if not records:
            continue
        print(f"\n  {sig} ({len(records)} signals):")
        for horizon in ["T+3m", "T+6m", "T+12m"]:
            valid = [r for r in records if horizon in r["forward"]]
            if not valid:
                continue
            if sig == "BUY":
                correct = sum(1 for r in valid if r["forward"][horizon]["return"] > 0)
            else:
                correct = sum(1 for r in valid if r["forward"][horizon]["return"] < 0)
            avg_ret = sum(r["forward"][horizon]["return"] for r in valid) / len(valid)
            acc = correct / len(valid) * 100
            print(f"    {horizon}: acc={acc:.1f}%, avg_ret={avg_ret:+.1%}, n={len(valid)}")

    return by_sig


b = analyze(baseline_results, "BASELINE (Original Rules)")
i = analyze(improved_results, "IMPROVED (With All 3 Improvements)")

# ============================================================
# Comparison summary
# ============================================================
print(f"\n{'=' * 70}")
print(f"  COMPARISON SUMMARY")
print(f"{'=' * 70}")

for horizon in ["T+3m", "T+6m", "T+12m"]:
    # BUY accuracy
    b_buy = [r for r in baseline_results if r["signal"] == "BUY" and horizon in r["forward"]]
    i_buy = [r for r in improved_results if r["signal"] == "BUY" and horizon in r["forward"]]

    if b_buy and i_buy:
        b_acc = sum(1 for r in b_buy if r["forward"][horizon]["return"] > 0) / len(b_buy) * 100
        i_acc = sum(1 for r in i_buy if r["forward"][horizon]["return"] > 0) / len(i_buy) * 100
        b_avg = sum(r["forward"][horizon]["return"] for r in b_buy) / len(b_buy) * 100
        i_avg = sum(r["forward"][horizon]["return"] for r in i_buy) / len(i_buy) * 100

        acc_delta = i_acc - b_acc
        avg_delta = i_avg - b_avg
        print(f"\n  BUY {horizon}:")
        print(f"    Baseline:  acc={b_acc:.1f}%, avg_ret={b_avg:+.1f}%, n={len(b_buy)}")
        print(f"    Improved:  acc={i_acc:.1f}%, avg_ret={i_avg:+.1f}%, n={len(i_buy)}")
        print(f"    Delta:     acc={acc_delta:+.1f}pp, avg_ret={avg_delta:+.1f}pp")

    # REDUCE accuracy
    b_red = [r for r in baseline_results if r["signal"] == "REDUCE" and horizon in r["forward"]]
    i_red = [r for r in improved_results if r["signal"] == "REDUCE" and horizon in r["forward"]]

    if b_red and i_red:
        b_acc = sum(1 for r in b_red if r["forward"][horizon]["return"] < 0) / len(b_red) * 100
        i_acc = sum(1 for r in i_red if r["forward"][horizon]["return"] < 0) / len(i_red) * 100
        print(f"\n  REDUCE {horizon}:")
        print(f"    Baseline:  acc={b_acc:.1f}%, n={len(b_red)}")
        print(f"    Improved:  acc={i_acc:.1f}%, n={len(i_red)}")
