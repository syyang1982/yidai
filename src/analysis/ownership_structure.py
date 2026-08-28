"""Ownership structure analysis module (advisory check for D7).

Checks for "barbarians at the gate" scenarios:
  - 无实际控制人: no single entity holds decisive control
  - 分散股权: widely dispersed ownership (no dominant shareholder)
  - 一致行动人: acting-in-concert groups that collectively control

Key insight for retail investors:
  A company with no clear controller is a potential takeover target.
  Acquirers typically pay a 20-40% premium, making this a positive signal
  for existing shareholders — the "barbarians at the gate" thesis.

Analysis categories:
  - has_controller: company has a clear controlling shareholder/group (>30%)
  - no_controller: no single shareholder/group holds >30% — potential target
  - dispersed: top shareholder <20% — high takeover potential
  - closely_held: top shareholder >50% — very low takeover risk

Severity (advisory, NOT a score penalty):
  - 'opportunity': no controller, potential takeover premium
  - 'stable': has controller, normal governance
  - 'concentrated_risk': very concentrated ownership (>60%), minority risk
"""

from __future__ import annotations


def analyze_controller_status(shareholders: list[dict]) -> dict:
    """Analyze whether a company has an actual controller.

    Args:
        shareholders: list of shareholder dicts, each with:
            - name: shareholder name
            - pct: holding percentage (e.g. 15.3 for 15.3%)
            - type: 'natural_person' / 'legal_entity' / 'state' / 'fund' / etc.
            - acting_in_concert: optional list of names that act together

    Returns:
        dict with keys:
            has_controller: bool
            controller_name: str or None
            controller_pct: float or None
            category: 'closely_held' / 'has_controller' / 'no_controller' / 'dispersed'
            top_shareholders: list of top 3 (name, pct) tuples
            opportunity: str — advisory message about takeover potential
            warnings: list of str — advisory warning lines
    """
    if not shareholders:
        return {
            "has_controller": False,
            "controller_name": None,
            "controller_pct": None,
            "category": "unknown",
            "top_shareholders": [],
            "opportunity": "无股东数据，无法判断",
            "warnings": ["⚠️ 无十大股东数据"],
        }

    # Sort by percentage descending
    sorted_sh = sorted(shareholders, key=lambda x: x.get("pct", 0), reverse=True)
    top3 = [(s["name"], s["pct"]) for s in sorted_sh[:3]]

    # Check for acting-in-concert groups
    # Group shareholders by acting_in_concert affiliation
    effective_pcts: dict[str, float] = {}
    for sh in sorted_sh:
        name = sh["name"]
        pct = sh.get("pct", 0)
        concert = sh.get("acting_in_concert")
        if concert:
            # Use the group leader name
            group_name = concert[0] if isinstance(concert, list) else str(concert)
            effective_pcts[group_name] = effective_pcts.get(group_name, 0) + pct
        else:
            effective_pcts[name] = effective_pcts.get(name, 0) + pct

    # Find the effective largest holder
    if effective_pcts:
        top_group_name = max(effective_pcts, key=effective_pcts.get)
        top_group_pct = effective_pcts[top_group_name]
    else:
        top_group_name = sorted_sh[0]["name"]
        top_group_pct = sorted_sh[0].get("pct", 0)

    # Second largest effective holder
    sorted_effective = sorted(effective_pcts.items(), key=lambda x: x[1], reverse=True)
    second_pct = sorted_effective[1][1] if len(sorted_effective) > 1 else 0

    # Classify
    warnings: list[str] = []
    opportunity = ""

    if top_group_pct > 60:
        # Very concentrated — low takeover risk, but minority shareholder risk
        category = "closely_held"
        has_controller = True
        controller_name = top_group_name
        controller_pct = top_group_pct
        opportunity = "股权高度集中，收购可能性极低"
        warnings.append(
            f"ℹ️ {top_group_name}持股{top_group_pct:.1f}%，股权高度集中"
        )
        warnings.append(
            "   散户需关注: 大股东利益输送风险、少数股东权益保护"
        )

    elif top_group_pct > 30:
        # Has a clear controller
        category = "has_controller"
        has_controller = True
        controller_name = top_group_name
        controller_pct = top_group_pct
        opportunity = "有明确实际控制人，收购可能性较低"

        # Check if second holder is close (potential challenge)
        if second_pct > 15 and (top_group_pct - second_pct) < 10:
            warnings.append(
                f"⚠️ 股权争夺风险: {top_group_name}({top_group_pct:.1f}%) "
                f"vs 第二大股东({second_pct:.1f}%)，差距较小"
            )
        else:
            warnings.append(
                f"ℹ️ {top_group_name}持股{top_group_pct:.1f}%，控制权稳固"
            )

    elif top_group_pct > 20:
        # No single controller, but not fully dispersed
        category = "no_controller"
        has_controller = False
        controller_name = None
        controller_pct = top_group_pct
        opportunity = "无实际控制人 — 存在收购/举牌可能"
        warnings.append(
            f"🔔 无实际控制人: 最大股东{top_group_name}仅持{top_group_pct:.1f}%"
        )
        warnings.append(
            "   潜在机会: 一旦被举牌/收购，散户可享受20-40%溢价"
        )
        if second_pct > 10:
            warnings.append(
                f"   第二大{sorted_effective[1][0]}持{second_pct:.1f}%，多方博弈"
            )

    else:
        # Dispersed — high takeover potential
        category = "dispersed"
        has_controller = False
        controller_name = None
        controller_pct = top_group_pct
        opportunity = "股权高度分散 — 优质收购标的"
        warnings.append(
            f"🔔 股权高度分散: 最大股东{top_group_name}仅持{top_group_pct:.1f}%"
        )
        warnings.append(
            "   🔥 \"门口的野蛮人\"信号强: 任何资金方均可通过二级市场举牌夺取控制权"
        )
        warnings.append(
            "   散户策略: 低位持有等待举牌溢价，或关注大宗交易异动"
        )

    return {
        "has_controller": has_controller,
        "controller_name": controller_name,
        "controller_pct": controller_pct,
        "category": category,
        "top_shareholders": top3,
        "opportunity": opportunity,
        "warnings": warnings,
        "effective_pcts": dict(sorted_effective[:5]),  # top 5 effective holders
    }


def format_ownership_structure(result: dict) -> str:
    """Format ownership structure analysis for terminal display.

    Returns:
        Multi-line string with analysis results.
    """
    if not result or result.get("category") == "unknown":
        return ""

    category = result.get("category", "")
    emoji_map = {
        "closely_held": "🔒",
        "has_controller": "👤",
        "no_controller": "🔔",
        "dispersed": "🔥",
    }
    emoji = emoji_map.get(category, "⚪")

    lines = [f"  {emoji} 股权结构分析:"]
    lines.append(f"    分类: {category}")
    lines.append(f"    {result.get('opportunity', '')}")

    if result.get("controller_name"):
        lines.append(
            f"    实控人: {result['controller_name']} ({result['controller_pct']:.1f}%)"
        )
    else:
        lines.append("    实控人: 无")

    # Top shareholders
    top = result.get("top_shareholders", [])
    if top:
        parts = [f"{name}({pct:.1f}%)" for name, pct in top[:3]]
        lines.append(f"    前三大: {', '.join(parts)}")

    for w in result.get("warnings", []):
        lines.append(f"    {w}")

    return "\n".join(lines)
