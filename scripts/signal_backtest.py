
import json
import math
from datetime import datetime, timedelta
from collections import defaultdict

# Load historical prices
with open("/home/frank/.hermes/yidai/reports/historical_prices.json") as f:
    all_data = json.load(f)

# ============================================================
# Signal Generation Model (Simplified)
# ============================================================
# Based on yidai's 8-dimension scoring philosophy but using
# price-based proxies for historical simulation:
#
# BUY conditions (score >= 33 equivalent):
#   - 6m momentum > 0 (price trending up)
#   - 12m momentum > -10% (not in severe downtrend)
#   - Price above 6m MA (trend confirmation)
#   - 3m momentum not too negative (>-15%)
#
# REDUCE conditions (score <= 16 equivalent):
#   - 12m momentum < -30% (severe downtrend)
#   - OR 6m momentum < -25% AND 3m momentum < -15%
#   - OR price below 12m MA AND 6m momentum < -20%
#
# HOLD otherwise

def compute_momentum(prices, idx, months):
    """Compute return over N months ending at idx."""
    if idx < months:
        return None
    p0 = prices[idx - months]["close"]
    p1 = prices[idx]["close"]
    if p0 <= 0:
        return None
    return (p1 - p0) / p0

def compute_ma(prices, idx, months):
    """Compute simple moving average."""
    if idx < months - 1:
        return None
    window = [prices[i]["close"] for i in range(idx - months + 1, idx + 1)]
    return sum(window) / len(window)

def generate_signal(prices, idx):
    """Generate BUY/HOLD/REDUCE signal at given index."""
    m3 = compute_momentum(prices, idx, 3)
    m6 = compute_momentum(prices, idx, 6)
    m12 = compute_momentum(prices, idx, 12)
    ma6 = compute_ma(prices, idx, 6)
    ma12 = compute_ma(prices, idx, 12)
    price = prices[idx]["close"]

    if any(v is None for v in [m3, m6]):
        return "HOLD", "insufficient_data"

    # REDUCE conditions
    if m12 is not None and m12 < -0.30:
        return "REDUCE", f"12m_momentum={m12:.1%}"
    if m6 < -0.25 and m3 < -0.15:
        return "REDUCE", f"6m={m6:.1%},3m={m3:.1%}"
    if ma12 is not None and price < ma12 and m6 < -0.20:
        return "REDUCE", f"below_12m_MA,6m={m6:.1%}"

    # BUY conditions
    buy_score = 0
    if m6 > 0:
        buy_score += 1
    if m12 is not None and m12 > -0.10:
        buy_score += 1
    if ma6 is not None and price > ma6:
        buy_score += 1
    if m3 > -0.15:
        buy_score += 1
    # Additional: strong momentum bonus
    if m6 > 0.15:
        buy_score += 1
    if m3 > 0.05:
        buy_score += 1

    if buy_score >= 5:
        return "BUY", f"score={buy_score},6m={m6:.1%},3m={m3:.1%}"

    return "HOLD", f"score={buy_score}"

# ============================================================
# Run Backtest
# ============================================================
results = []
evaluation_dates = []

for ticker, info in all_data.items():
    name = info["name"]
    prices = info["prices"]
    
    # Filter to 2024.1 onwards for evaluation
    for idx in range(len(prices)):
        dt = prices[idx]["date"]
        if dt < "2024-01":
            continue
        
        signal, reason = generate_signal(prices, idx)
        p0 = prices[idx]["close"]
        
        # Track forward returns at T+3, T+6, T+9, T+12 months
        forward = {}
        for months in [3, 6, 9, 12]:
            future_idx = idx + months
            if future_idx < len(prices):
                pf = prices[future_idx]["close"]
                ret = (pf - p0) / p0
                forward[f"T+{months}m"] = {
                    "price": pf,
                    "return": round(ret, 4),
                    "date": prices[future_idx]["date"]
                }
        
        results.append({
            "ticker": ticker,
            "name": name,
            "date": dt,
            "price": p0,
            "signal": signal,
            "reason": reason,
            "forward": forward
        })

# Save raw results
with open("/home/frank/.hermes/yidai/reports/backtest_results.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Total signals generated: {len(results)}")

# ============================================================
# Statistical Analysis
# ============================================================
by_signal = defaultdict(list)
for r in results:
    by_signal[r["signal"]].append(r)

print(f"\nSignal distribution:")
for sig in ["BUY", "HOLD", "REDUCE"]:
    print(f"  {sig}: {len(by_signal[sig])}")

# Accuracy by signal type and horizon
print(f"\n{'='*70}")
print(f"  Signal Accuracy (directional correctness)")
print(f"{'='*70}")

for sig in ["BUY", "HOLD", "REDUCE"]:
    records = by_signal[sig]
    if not records:
        continue
    
    print(f"\n  {sig} ({len(records)} signals):")
    for horizon in ["T+3m", "T+6m", "T+9m", "T+12m"]:
        valid = [r for r in records if horizon in r["forward"]]
        if not valid:
            continue
        
        if sig == "BUY":
            correct = sum(1 for r in valid if r["forward"][horizon]["return"] > 0)
        elif sig == "REDUCE":
            correct = sum(1 for r in valid if r["forward"][horizon]["return"] < 0)
        else:
            correct = sum(1 for r in valid if abs(r["forward"][horizon]["return"]) < 0.15)
        
        avg_ret = sum(r["forward"][horizon]["return"] for r in valid) / len(valid)
        acc = correct / len(valid) * 100
        
        # Median return
        rets = sorted(r["forward"][horizon]["return"] for r in valid)
        median_ret = rets[len(rets)//2]
        
        print(f"    {horizon}: acc={acc:.1f}% ({correct}/{len(valid)}), "
              f"avg_ret={avg_ret:+.1%}, median={median_ret:+.1%}, n={len(valid)}")

# Average returns by signal type
print(f"\n{'='*70}")
print(f"  Average Returns by Signal Type")
print(f"{'='*70}")

for sig in ["BUY", "HOLD", "REDUCE"]:
    records = by_signal[sig]
    if not records:
        continue
    
    print(f"\n  {sig}:")
    for horizon in ["T+3m", "T+6m", "T+9m", "T+12m"]:
        valid = [r for r in records if horizon in r["forward"]]
        if not valid:
            continue
        
        rets = [r["forward"][horizon]["return"] for r in valid]
        avg = sum(rets) / len(rets)
        wins = sum(1 for r in rets if r > 0)
        losses = sum(1 for r in rets if r <= 0)
        
        print(f"    {horizon}: avg={avg:+.1%}, wins={wins}, losses={losses}, "
              f"win_rate={wins/(wins+losses)*100:.0f}%")

# Per-company analysis
print(f"\n{'='*70}")
print(f"  Per-Company BUY Signal Performance")
print(f"{'='*70}")

company_buys = defaultdict(list)
for r in by_signal["BUY"]:
    company_buys[f"{r['name']}({r['ticker']})"].append(r)

for company, records in sorted(company_buys.items()):
    for horizon in ["T+3m", "T+6m", "T+12m"]:
        valid = [r for r in records if horizon in r["forward"]]
        if not valid:
            continue
        avg_ret = sum(r["forward"][horizon]["return"] for r in valid) / len(valid)
        print(f"  {company:20s} {horizon}: {avg_ret:+.1%} (n={len(valid)})")
    print()
