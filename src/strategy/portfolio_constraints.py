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
                    "pct": pct,
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
                    "pct": pct,
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
                    "pct": pct,
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
                    "pct": pct,
                    "limit": self.max_correlation_group_pct,
                    "value_hkd": group_value,
                })
        return violations

    # ── risk budget checks ────────────────────────────────────────

    def check_volatility(self, holdings: List[dict]) -> List[dict]:
        """Flag holdings with annualised volatility above 60%.

        Each holding must include ``volatility_annual`` (0-1 float, e.g. 0.6 = 60%).
        """
        violations: List[dict] = []
        for h in holdings:
            vol = h.get("volatility_annual", 0)
            if vol > 0.60:
                violations.append({
                    "type": "high_volatility",
                    "ticker": h.get("ticker"),
                    "name": h.get("name"),
                    "volatility": vol,
                    "limit": 0.60,
                    "message": f"{h.get('name')} 年化波动率{vol:.0%} > 60%上限，建议减半仓",
                })
        return violations

    def check_liquidity(self, holdings: List[dict]) -> List[dict]:
        """Flag holdings with average daily turnover below HK$100M.

        Each holding must include ``avg_daily_volume_hkd``.
        """
        violations: List[dict] = []
        for h in holdings:
            vol = h.get("avg_daily_volume_hkd", float("inf"))
            if vol < 100_000_000:
                violations.append({
                    "type": "low_liquidity",
                    "ticker": h.get("ticker"),
                    "name": h.get("name"),
                    "volume": vol,
                    "limit": 100_000_000,
                    "message": f"{h.get('name')} 日均成交额{vol / 1e8:.1f}亿 < 1亿，流动性不足",
                })
        return violations

    def check_stop_loss(self, holdings: List[dict]) -> List[dict]:
        """Flag holdings that breach stop-loss conditions.

        Each holding should include:
        - cost_basis: entry price
        - current_price: latest price
        - stop_loss_price (optional): explicit stop level
        - signal (optional): current signal string (e.g. ``"REDUCE"``)

        Three stop-loss triggers:
        1. Hard stop — realised loss > 50 %
        2. Price stop — current price <= stop_loss_price
        3. Fundamental + technical — signal == REDUCE and loss > 20 %
        """
        violations: List[dict] = []
        for h in holdings:
            cost = h.get("cost_basis", 0)
            current = h.get("current_price", 0)
            stop = h.get("stop_loss_price")
            signal = h.get("signal", "")

            if cost > 0 and current > 0:
                pnl = (current - cost) / cost

                # 1. Hard stop: loss > 50 %
                if pnl < -0.50:
                    violations.append({
                        "type": "hard_stop_loss",
                        "ticker": h.get("ticker"),
                        "name": h.get("name"),
                        "pnl": pnl,
                        "message": f"{h.get('name')} 亏损{pnl:.0%}，触发硬止损(-50%)",
                    })

                # 2. Stop-loss price triggered
                if stop and current <= stop:
                    violations.append({
                        "type": "stop_loss_triggered",
                        "ticker": h.get("ticker"),
                        "name": h.get("name"),
                        "current": current,
                        "stop": stop,
                        "message": f"{h.get('name')} 当前价{current} <= 止损价{stop}",
                    })

                # 3. Fundamental deterioration + technical breakdown
                if signal == "REDUCE" and pnl < -0.20:
                    violations.append({
                        "type": "fundamental_deterioration",
                        "ticker": h.get("ticker"),
                        "name": h.get("name"),
                        "signal": signal,
                        "pnl": pnl,
                        "message": f"{h.get('name')} 信号REDUCE + 亏损{pnl:.0%}，基本面+技术双确认止损",
                    })
        return violations

    # ── aggregate check ───────────────────────────────────────────

    def check_all(self, holdings: List[dict]) -> dict:
        """Run every constraint check and return a combined result dict."""
        position_violations = self.check_position_limits(holdings)
        sector_violations = self.check_sector_concentration(holdings)
        market_violations = self.check_market_exposure(holdings)
        correlation_violations = self.check_correlation_groups(holdings)
        volatility_violations = self.check_volatility(holdings)
        liquidity_violations = self.check_liquidity(holdings)
        stop_loss_violations = self.check_stop_loss(holdings)

        total = (
            len(position_violations)
            + len(sector_violations)
            + len(market_violations)
            + len(correlation_violations)
            + len(volatility_violations)
            + len(liquidity_violations)
            + len(stop_loss_violations)
        )

        return {
            "position_violations": position_violations,
            "sector_violations": sector_violations,
            "market_violations": market_violations,
            "correlation_violations": correlation_violations,
            "volatility_violations": volatility_violations,
            "liquidity_violations": liquidity_violations,
            "stop_loss_violations": stop_loss_violations,
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

        vv = result["volatility_violations"]
        if vv:
            lines.append(f"\n⚠️  波动率过高 ({len(vv)}):")
            for v in vv:
                lines.append(f"  {v['message']}")
        else:
            lines.append("\n✅ 波动率合规")

        lv = result["liquidity_violations"]
        if lv:
            lines.append(f"\n⚠️  流动性不足 ({len(lv)}):")
            for v in lv:
                lines.append(f"  {v['message']}")
        else:
            lines.append("\n✅ 流动性合规")

        slv = result["stop_loss_violations"]
        if slv:
            lines.append(f"\n🚨 止损告警 ({len(slv)}):")
            for v in slv:
                lines.append(f"  {v['message']}")
        else:
            lines.append("\n✅ 无止损触发")

        lines.append(f"\n总违规数: {result['total_violations']}")
        lines.append("=" * 50)
        return "\n".join(lines)
