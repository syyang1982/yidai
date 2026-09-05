#!/usr/bin/env python3
"""进一步改进回测 — 增加市场regime检测 + 反转BUY信号。

改进4: 市场regime过滤
  - 计算市场整体(所有公司平均)的6月动量
  - 熊市(regime < -15%): 放宽REDUCE, 收紧BUY
  - 牛市(regime > +15%): 放宽BUY, 收紧REDUCE
  - 震荡: 默认规则

改进5: 反转BUY信号
  - 当REDUCE后价格企稳(3月动量转正)时,触发BUY
  - 利用均值回归效应(回测发现REDUCE后12月+116%)
"""
import json
from collections import defaultdict

with open("/home/frank/.hermes/yidai/reports/oos_prices.json") as f:
    all_data = json.load(f)

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
    if idx < window:
        return None
    recent = [prices[i]["close"] for i in range(idx - window + 1, idx + 1)]
    current = prices[idx]["close"]
    below = sum(1 for p in recent if p < current)
    return below / len(recent)


def compute_market_regime(all_data, target_date):
    """Compute average 6-month momentum across all companies at target_date."""
    momentums = []
    for ticker, info in all_data.items():
        prices = info["prices"]
        for idx, p in enumerate(prices):
            if p["date"] == target_date:
                m6 = compute_momentum(prices, idx, 6)
                if m6 is not None:
                    momentums.append(m6)
                break
    if not momentums:
        return 0.0
    return sum(momentums) / len(momentums)


def generate_signal_v3(prices, idx, prev_signals, market_regime):
    """V3: with market regime + reversal BUY."""
    m3 = compute_momentum(prices, idx, 3)
    m6 = compute_momentum(prices, idx, 6)
    m12 = compute_momentum(prices, idx, 12)
    ma6 = compute_ma(prices, idx, 6)
    pe_pct = compute_pe_percentile(prices, idx)
    cfg = default_cfg

    if any(v is None for v in [m3, m6]):
        return "HOLD", "insufficient"

    # --- REDUCE conditions ---
    # In bear market: more sensitive (lower thresholds)
    reduce_threshold_12m = -0.25 if market_regime < -0.15 else -0.30
    reduce_threshold_6m = -0.20 if market_regime < -0.15 else -0.25

    if m12 is not None and m12 < reduce_threshold_12m:
        return "REDUCE", f"12m={m12:.1%}"
    if m6 < reduce_threshold_6m and m3 < -0.15:
        return "REDUCE", f"6m={m6:.1%}"

    # --- Improvement 5: Reversal BUY ---
    # After REDUCE, if price stabilizes (3m momentum turns positive),
    # this is a strong BUY signal exploiting mean-reversion
    last_reduce = prev_signals.get("last_reduce_idx")
    if last_reduce is not None:
        months_since = idx - last_reduce
        if 2 <= months_since <= 6 and m3 > 0.05:
            # Price recovering after REDUCE — reversal BUY
            return "BUY_REVERSAL", f"reduce+{months_since}m,m3={m3:.1%}"

    # --- Improvement 4: Regime-adjusted BUY ---
    # In bear market: require higher buy score
    buy_threshold = cfg["buy_threshold"]
    if market_regime < -0.15:
        buy_threshold += 2  # Harder to trigger BUY in bear market
    elif market_regime > 0.15:
        buy_threshold -= 1  # Easier in bull market

    buy_score = 0
    if m6 > 0: buy_score += 1
    if m12 is not None and m12 > -0.10: buy_score += 1
    if ma6 is not None and prices[idx]["close"] > ma6: buy_score += 1
    if m3 > -0.15: buy_score += 1
    if m6 > 0.15: buy_score += 1
    if m3 > 0.05: buy_score += 1

    if buy_score >= buy_threshold:
        # PE guard
        pe_cap = cfg["pe_cap"]
        if market_regime < -0.15:
            pe_cap = 0.70  # Stricter in bear market
        if pe_pct is not None and pe_pct > pe_cap:
            return "HOLD", f"val_guard:{pe_pct:.0%}"

        # REDUCE protection
        if last_reduce is not None:
            months_since = idx - last_reduce
            if months_since * 30 < cfg["reduce_days"]:
                return "HOLD", f"reduce_protect:{months_since}m"

        return "BUY", f"score={buy_score}"

    return "HOLD", f"score={buy_score}"


# Run V3 backtest
results_v3 = []

for ticker, info in all_data.items():
    name = info["name"]
    prices = info["prices"]
    prev_signals = {}

    for idx in range(len(prices)):
        dt = prices[idx]["date"]
        if dt < "2025-09":
            continue

        # Compute market regime at this date
        market_regime = compute_market_regime(all_data, dt)

        p0 = prices[idx]["close"]
        sig, reason = generate_signal_v3(prices, idx, prev_signals, market_regime)

        if sig in ("REDUCE",):
            prev_signals["last_reduce_idx"] = idx

        forward = {}
        for months in [3, 6]:
            future_idx = idx + months
            if future_idx < len(prices):
                pf = prices[future_idx]["close"]
                ret = (pf - p0) / p0
                forward[f"T+{months}m"] = {"return": round(ret, 4)}

        results_v3.append({
            "ticker": ticker, "name": name, "signal": sig,
            "forward": forward, "date": dt, "regime": market_regime,
        })

# Analyze
by_sig = defaultdict(list)
for r in results_v3:
    by_sig[r["signal"]].append(r)

print(f"V3 Signals: BUY={len(by_sig.get('BUY',[]))}, BUY_REVERSAL={len(by_sig.get('BUY_REVERSAL',[]))}, HOLD={len(by_sig.get('HOLD',[]))}, REDUCE={len(by_sig.get('REDUCE',[]))}")

for sig_type in ["BUY", "BUY_REVERSAL"]:
    records = by_sig.get(sig_type, [])
    if not records:
        continue
    print(f"\n  {sig_type} ({len(records)} signals):")
    for horizon in ["T+3m", "T+6m"]:
        valid = [r for r in records if horizon in r["forward"]]
        if not valid:
            continue
        correct = sum(1 for r in valid if r["forward"][horizon]["return"] > 0)
        avg_ret = sum(r["forward"][horizon]["return"] for r in valid) / len(valid)
        acc = correct / len(valid) * 100
        print(f"    {horizon}: acc={acc:.1f}%, avg_ret={avg_ret:+.1%}, n={len(valid)}")

# Per-company for BUY_REVERSAL
reversal_buys = by_sig.get("BUY_REVERSAL", [])
if reversal_buys:
    print(f"\n  BUY_REVERSAL per-company:")
    by_co = defaultdict(list)
    for r in reversal_buys:
        by_co[f"{r['name']}({r['ticker']})"].append(r)
    for company, records in sorted(by_co.items()):
        for horizon in ["T+3m", "T+6m"]:
            valid = [r for r in records if horizon in r["forward"]]
            if not valid:
                continue
            avg_ret = sum(r["forward"][horizon]["return"] for r in valid) / len(valid)
            print(f"    {company:20s} {horizon}: {avg_ret:+.1%} (n={len(valid)})")

# Compare all versions
print(f"\n{'=' * 70}")
print(f"  FULL COMPARISON (OOS Sept 2025+)")
print(f"{'=' * 70}")

# Load baseline and improved results from previous run
with open("/home/frank/.hermes/yidai/reports/oos_prices.json") as f:
    pass  # Already loaded

# Re-run baseline for comparison
baseline_results = []
improved_results = []

for ticker, info in all_data.items():
    prices = info["prices"]
    for idx in range(len(prices)):
        dt = prices[idx]["date"]
        if dt < "2025-09":
            continue
        p0 = prices[idx]["close"]
        m3 = compute_momentum(prices, idx, 3)
        m6 = compute_momentum(prices, idx, 6)
        m12 = compute_momentum(prices, idx, 12)
        ma6 = compute_ma(prices, idx, 6)
        pe_pct = compute_pe_percentile(prices, idx)

        # Baseline
        sig_b = "HOLD"
        if m3 is not None and m6 is not None:
            if m12 is not None and m12 < -0.30:
                sig_b = "REDUCE"
            elif m6 is not None and m6 < -0.25 and m3 < -0.15:
                sig_b = "REDUCE"
            else:
                bs = 0
                if m6 > 0: bs += 1
                if m12 is not None and m12 > -0.10: bs += 1
                if ma6 is not None and p0 > ma6: bs += 1
                if m3 > -0.15: bs += 1
                if m6 > 0.15: bs += 1
                if m3 > 0.05: bs += 1
                if bs >= 5: sig_b = "BUY"

        forward = {}
        for months in [3, 6]:
            fi = idx + months
            if fi < len(prices):
                forward[f"T+{months}m"] = {"return": round((prices[fi]["close"] - p0) / p0, 4)}
        baseline_results.append({"signal": sig_b, "forward": forward})

print(f"\n  {'Version':<20} {'BUY n':<8} {'T+3 acc':<10} {'T+3 avg':<10} {'T+6 acc':<10} {'T+6 avg':<10}")
print(f"  {'-' * 68}")

for label, res in [("Baseline", baseline_results), ("V3 (regime+reversal)", results_v3)]:
    for sig_type in ["BUY", "BUY_REVERSAL"]:
        records = [r for r in res if r["signal"] == sig_type]
        if not records:
            continue
        for horizon in ["T+3m", "T+6m"]:
            valid = [r for r in records if horizon in r["forward"]]
            if not valid:
                continue
            correct = sum(1 for r in valid if r["forward"][horizon]["return"] > 0)
            avg_ret = sum(r["forward"][horizon]["return"] for r in valid) / len(valid)
            acc = correct / len(valid) * 100
            print(f"  {label+' '+sig_type:<25} {len(valid):<8} {acc:.1f}%{'':<4} {avg_ret:+.1f}%{'':<4}", end="")
        print()

# REDUCE comparison
for label, res in [("Baseline", baseline_results), ("V3 (regime+reversal)", results_v3)]:
    records = [r for r in res if r["signal"] == "REDUCE"]
    if not records:
        continue
    for horizon in ["T+3m", "T+6m"]:
        valid = [r for r in records if horizon in r["forward"]]
        if not valid:
            continue
        correct = sum(1 for r in valid if r["forward"][horizon]["return"] < 0)
        acc = correct / len(valid) * 100
    print(f"  {label+' REDUCE':<25} {len(records):<8} ", end="")
    for horizon in ["T+3m", "T+6m"]:
        valid = [r for r in records if horizon in r["forward"]]
        if valid:
            correct = sum(1 for r in valid if r["forward"][horizon]["return"] < 0)
            acc = correct / len(valid) * 100
            avg_ret = sum(r["forward"][horizon]["return"] for r in valid) / len(valid)
            print(f"{acc:.1f}%{'':<4} {avg_ret:+.1f}%{'':<4}", end="")
    print()
