"""极简终端表格工具：CJK 双宽对齐。

刻意只做一件事：把行渲染成等宽列，CJK/emoji 按 2 列计。
不引第三方依赖，供 ops/feedback 等报告类模块复用。
"""
from __future__ import annotations

import unicodedata
from typing import Iterable, List, Optional, Sequence


def display_width(s) -> int:
    """字符串在终端中的显示宽度（CJK/全角字符占 2 列，emoji 也按 2 列计）。"""
    w = 0
    for ch in str(s):
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        elif unicodedata.combining(ch):
            continue
        else:
            # emoji 等宽字符（多数落在 'N'/'W' 之外），保守按 2 列计
            o = ord(ch)
            if 0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF:
                w += 2
            else:
                w += 1
    return w


def _pad(s, width: int, align: str = "left") -> str:
    s = str(s)
    pad = width - display_width(s)
    if pad <= 0:
        return s
    if align == "right":
        return " " * pad + s
    if align == "center":
        left = pad // 2
        return " " * left + s + " " * (pad - left)
    return s + " " * pad


def col_widths(rows: Sequence[Sequence], headers: Sequence[str]) -> List[int]:
    """列宽 = max(表头显示宽度, 各行显示宽度)。"""
    n = len(headers)
    widths = [display_width(h) for h in headers]
    for r in rows:
        for i in range(min(n, len(r))):
            widths[i] = max(widths[i], display_width(r[i]))
    return widths


def row(values: Iterable, sep: str = "  ", aligns: Optional[Sequence[str]] = None) -> str:
    """渲染一行，列宽按内容自适应不补空（配合 table() 使用可自动对齐）。"""
    vals = [str(v) for v in values]
    aligns = list(aligns) if aligns else ["left"] * len(vals)
    return sep.join(_pad(v, display_width(v), a) for v, a in zip(vals, aligns))


def rule(widths: Sequence[int], ch: str = "─", sep: str = "  ") -> str:
    """按给定列宽渲染分隔线。"""
    return sep.join(ch * w for w in widths)


def table(headers: Sequence[str], rows: Sequence[Sequence], aligns: Optional[Sequence[str]] = None) -> str:
    """渲染一张自动对齐的表（表头 + 分隔线 + 数据行）。"""
    aligns = list(aligns) if aligns else ["left"] * len(headers)
    widths = col_widths(rows, headers)
    out = [
        "  " + "  ".join(_pad(h, w, a) for h, w, a in zip(headers, widths, aligns)),
        "  " + rule(widths),
    ]
    for r in rows:
        out.append("  " + "  ".join(_pad(v, w, a) for v, w, a in zip(r, widths, aligns)))
    return "\n".join(out)
