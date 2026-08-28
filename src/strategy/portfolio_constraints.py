"""Portfolio constraint checks — position limits, sector/market concentration, correlation groups."""
from __future__ import annotations

from collections import defaultdict
from typing import List, Optional


class PortfolioConstraints:
    """Checks portfolio-level constraints and reports violations."""

    def __init__(
        self,
        max_single_pct: float = 25,
        max_sector_pct: float = 40,
        max_market_pct: float = 70,
        max_correlation_group_pct: float = 35,
    ):
        self.max_single_pct: float = max_single_pct
        self.max_sector_pct: float = max_sector_pct
        self.max_market_pct: float = max_market_pct
        self.max_correlation_group_pct: float = max_correlation_group_pct
        self._correlation_groups: List[dict] = []

    # ── correlation group management ──────────────────────────────

    def add_correlation_group(self, name: str, tickers: List[str], reason: str) -> None:
        """Register a group of tickers that are highly correlated."""
        self._correlation_groups.append({
            "name": name,
            "tickers": set(tickers),
            "reason": reason,
        })

    # ── internal helpers ──────────────────────────────────────────

    @staticmethod
    def _total_value(holdings: List[dict]) -> float:
        return sum(h["value_hkd"] for h in holdings)

    @staticmethod
    def _pct(value: float, total: float) -> float:
        if total == 0:
            return 0.0
        return value / total * 100

    # ── individual checks ─────────────────────────────────────────

    def check_position_limits(self, holdings: List[dict]) -> List[dict]:
        """Flag any single position exceeding max_single_pct."""
        total = self._total_value(holdings)
        violations = []
        for h in holdings:
            pct = self._pct(h["value_hkd"], total)
            if pct > self.max_single_pct:
                violations.append({
                    "ticker": h["ticker"],
                    "name": h.get("name", ""),
                    "pct": round(pct, 2),
                    "limit": self.max_single_pct,
                    "value_hkd": h["value_hkd"],
                })
        return violations

    def check_sector_concentration(self, holdings: List[dict]) -> List[dict]:
        """Flag sectors whose aggregate weight exceeds max_sector_pct."""
        total = self._total_value(holdings)
        sector_values: dict[str, float] = defaultdict(float)
        for h in holdings:
            sector_values[h.get("sector", "未知")] += h["value_hkd"]

        violations = []
        for sector, value in sector_values.items():
            pct = self._pct(value, total)
            if pct > self.max_sector_pct:
                violations.append({
                    "sector": sector,
                    "pct": round(pct, 2),
                    "limit": self.max_sector_pct,
                    "value_hkd": value,
                })
        return violations

    def check_market_exposure(self, holdings: List[dict]) -> List[dict]:
        """Flag markets whose aggregate weight exceeds max_market_pct."""
        total = self._total_value(holdings)
        market_values: dict[str, float] = defaultdict(float)
        for h in holdings:
            market_values[h.get("market", "未知")] += h["value_hkd"]

        violations = []
        for market, value in market_values.items():
            pct = self._pct(value, total)
            if pct > self.max_market_pct:
                violations.append({
                    "market": market,
                    "pct": round(pct, 2),
                    "limit": self.max_market_pct,
                    "value_hkd": value,
                })
        return violations

    def check_correlation_groups(self, holdings: List[dict]) -> List[dict]:
        """Flag correlation groups whose aggregate weight exceeds max_correlation_group_pct."""
        total = self._total_value(holdings)
        ticker_value = {h["ticker"]: h["value_hkd"] for h in holdings}

        violations = []
        for group in self._correlation_groups:
            group_value = sum(
                ticker_value.get(t, 0) for t in group["tickers"]
            )
            pct = self._pct(group_value, total)
            if pct > self.max_correlation_group_pct:
                violations.append({
                    "group": group["name"],
                    "reason": group["reason"],
                    "pct": round(pct, 2),
                    "limit": self.max_correlation_group_pct,
                    "value_hkd": group_value,
                })
        return violations

    # ── aggregate check ───────────────────────────────────────────

    def check_all(self, holdings: List[dict]) -> dict:
        """Run every constraint check and return a combined result dict."""
        position_violations = self.check_position_limits(holdings)
        sector_violations = self.check_sector_concentration(holdings)
        market_violations = self.check_market_exposure(holdings)
        correlation_violations = self.check_correlation_groups(holdings)

        total = (
            len(position_violations)
            + len(sector_violations)
            + len(market_violations)
            + len(correlation_violations)
        )

        return {
            "position_violations": position_violations,
            "sector_violations": sector_violations,
            "market_violations": market_violations,
            "correlation_violations": correlation_violations,
            "total_violations": total,
        }

    # ── formatting ────────────────────────────────────────────────

    def format_report(self, result: dict) -> str:
        """Produce a human-readable text report from check_all() output."""
        lines: list[str] = []
        lines.append("=" * 50)
        lines.append("组合约束检查报告")
        lines.append("=" * 50)

        pv = result["position_violations"]
        if pv:
            lines.append(f"\n⚠️  仓位超限 ({len(pv)}):")
            for v in pv:
                lines.append(
                    f"  {v['ticker']} {v['name']}: {v['pct']}% > {v['limit']}% "
                    f"(HK${v['value_hkd']:,.0f})"
                )
        else:
            lines.append("\n✅ 仓位占比均在限内")

        sv = result["sector_violations"]
        if sv:
            lines.append(f"\n⚠️  行业集中度过高 ({len(sv)}):")
            for v in sv:
                lines.append(
                    f"  {v['sector']}: {v['pct']}% > {v['limit']}% "
                    f"(HK${v['value_hkd']:,.0f})"
                )
        else:
            lines.append("\n✅ 行业集中度合规")

        mv = result["market_violations"]
        if mv:
            lines.append(f"\n⚠️  市场暴露过高 ({len(mv)}):")
            for v in mv:
                lines.append(
                    f"  {v['market']}: {v['pct']}% > {v['limit']}% "
                    f"(HK${v['value_hkd']:,.0f})"
                )
        else:
            lines.append("\n✅ 市场暴露合规")

        cv = result["correlation_violations"]
        if cv:
            lines.append(f"\n⚠️  相关性组超限 ({len(cv)}):")
            for v in cv:
                lines.append(
                    f"  {v['group']}: {v['pct']}% > {v['limit']}% — {v['reason']}"
                )
        else:
            lines.append("\n✅ 相关性组合规")

        lines.append(f"\n总违规数: {result['total_violations']}")
        lines.append("=" * 50)
        return "\n".join(lines)
