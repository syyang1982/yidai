"""
Investment Knowledge Base for the 意怠工程 (Yidai) project.

File-based knowledge management system that stores:
  - Company profiles  (companies/{ticker}.md)
  - Decision journal  (journal.md)
  - Cross-company lessons (lessons.md)
  - Investment principles (principles.md)

All user-facing text is in Chinese.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Dimension name mapping (Chinese labels)
# ---------------------------------------------------------------------------

_DIM_NAMES = {
    "盈利": "盈利",
    "健康": "健康",
    "现金流": "现金流",
    "估值": "估值",
    "成长": "成长",
    "股东": "股东",
    "战略": "战略",
}

_DIM_ORDER = ["盈利", "健康", "现金流", "估值", "成长", "股东", "战略"]

# Score-to-key mapping for accepting various key formats
_SCORE_KEYS = {
    "profitability": "盈利",
    "profitability_score": "盈利",
    "盈利": "盈利",
    "health": "健康",
    "health_score": "健康",
    "健康": "健康",
    "cashflow": "现金流",
    "cashflow_score": "现金流",
    "现金流": "现金流",
    "valuation": "估值",
    "valuation_score": "估值",
    "估值": "估值",
    "growth": "成长",
    "growth_score": "成长",
    "成长": "成长",
    "ownership": "股东",
    "ownership_score": "股东",
    "股东": "股东",
    "strategy": "战略",
    "strategy_score": "战略",
    "战略": "战略",
}


# ---------------------------------------------------------------------------
# Helper: normalize score keys to Chinese dimension names
# ---------------------------------------------------------------------------

def _normalize_scores(scores: dict) -> dict:
    """Convert various key formats to {dim_name: score} dict."""
    result = {}
    for key, val in scores.items():
        normalized = _SCORE_KEYS.get(key)
        if normalized is not None:
            result[normalized] = int(val)
    return result


# ---------------------------------------------------------------------------
# Helper: compute grade and signal (mirrors src/data/models.py)
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (33, "A"),
    (26, "B"),
    (17, "C"),
    (9, "D"),
    (0, "F"),
]


def _compute_grade(total: int) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if total >= threshold:
            return letter
    return "F"


def _compute_signal(total: int, scores: dict) -> str:
    """Compute BUY / HOLD / WATCH / REDUCE signal from scores dict."""
    prof = scores.get("\u76c8\u5229", 0)
    health = scores.get("\u5065\u5eb7", 0)
    cf = scores.get("\u73b0\u91d1\u6d41", 0)
    val = scores.get("\u4f30\u503c", 0)
    grow = scores.get("\u6210\u957f", 0)
    div = scores.get("\u5206\u7ea2", 0)
    own = scores.get("\u80a1\u4e1c", 0)
    strat = scores.get("\u6218\u7565", 0)
    all_scores = [prof, health, cf, val, grow, own, strat]

    # Critical dimension failures
    if health < 2 or cf < 2 or own < 1:
        return "REDUCE"
    # Very low total (adjusted for 8-dim)
    if total <= 16:
        return "REDUCE"
    # Any single dimension critically low
    if any(s < 2 for s in all_scores):
        return "REDUCE"
    # Strong buy signal (adjusted for 8-dim)
    # 审计发现: 健康/成长高分有预测力，增加门槛排除quality trap
    if total >= 33 and val >= 4 and health >= 3 and grow >= 3:
        return "BUY"
    # Hold-worthy (adjusted for 8-dim)
    if total >= 17:
        return "HOLD"
    # Default
    return "WATCH"


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """File-based investment knowledge base.

    Directory structure:
        knowledge/
        ├── companies/           # One file per company
        │   ├── 01810.HK.md     # Xiaomi
        │   └── ...
        ├── lessons.md           # Cross-company lessons
        ├── principles.md        # Investment principles (evolving)
        └── journal.md           # Decision journal (all companies)
    """

    def __init__(self, base_dir: str = None):
        """Initialize knowledge base.

        Default base_dir: ~/.hermes/yidai/knowledge/
        Creates directory structure if not exists.
        """
        if base_dir is None:
            home = os.path.expanduser("~")
            base_dir = os.path.join(home, ".hermes", "yidai", "knowledge")
        self.base_dir = base_dir
        self.companies_dir = os.path.join(base_dir, "companies")
        self.lessons_path = os.path.join(base_dir, "lessons.md")
        self.principles_path = os.path.join(base_dir, "principles.md")
        self.journal_path = os.path.join(base_dir, "journal.md")

        # Create directories
        os.makedirs(self.companies_dir, exist_ok=True)

        # Create stub files if not exist
        for path in [self.lessons_path, self.principles_path, self.journal_path]:
            if not os.path.exists(path):
                self._write_markdown(path, self._init_file_content(path))

    # ------------------------------------------------------------------
    # File init templates
    # ------------------------------------------------------------------

    def _init_file_content(self, path: str) -> str:
        if path == self.lessons_path:
            return "# 跨公司经验教训\n\n"
        elif path == self.principles_path:
            return "# 投资原则\n\n"
        elif path == self.journal_path:
            return "# 决策日志\n\n"
        return ""

    # ------------------------------------------------------------------
    # Helper: file I/O
    # ------------------------------------------------------------------

    def _read_markdown(self, path: str) -> str:
        """Read file content."""
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _write_markdown(self, path: str, content: str) -> None:
        """Write file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _company_path(self, ticker: str) -> str:
        """Get the file path for a company profile."""
        return os.path.join(self.companies_dir, f"{ticker}.md")

    # ------------------------------------------------------------------
    # Helper: parse markdown table
    # ------------------------------------------------------------------

    def _parse_table(self, content: str, table_header: str) -> List[dict]:
        """Find a markdown table that follows ``table_header`` and parse it.

        Returns list of dicts, one per data row.
        """
        # Find the header line of the table after the section
        # Look for pattern: | header1 | header2 | ...
        lines = content.split("\n")
        header_idx = None
        for i, line in enumerate(lines):
            if table_header in line:
                # Search for the next table starting with |
                for j in range(i + 1, min(i + 20, len(lines))):
                    stripped = lines[j].strip()
                    if stripped.startswith("|") and "------" not in stripped:
                        header_idx = j
                        break
                break

        if header_idx is None:
            return []

        # Parse header
        headers = [h.strip() for h in lines[header_idx].split("|") if h.strip()]

        # Skip separator line
        data_start = header_idx + 1
        if data_start < len(lines) and "---" in lines[data_start]:
            data_start += 1

        # Parse data rows
        rows = []
        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= len(headers):
                row = {}
                for h, c in zip(headers, cells):
                    row[h] = c
                rows.append(row)

        return rows

    # ------------------------------------------------------------------
    # Helper: format markdown table
    # ------------------------------------------------------------------

    def _format_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Format a markdown table."""
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(cell))

        def _fmt_row(cells):
            parts = []
            for i, cell in enumerate(cells):
                w = col_widths[i] if i < len(col_widths) else len(cell)
                parts.append(f" {cell:<{w}} ")
            return "|" + "|".join(parts) + "|"

        lines = []
        lines.append(_fmt_row(headers))
        sep_parts = []
        for w in col_widths:
            sep_parts.append("-" * (w + 2))
        lines.append("|" + "|".join(sep_parts) + "|")
        for row in rows:
            lines.append(_fmt_row(row))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helper: update a section in markdown
    # ------------------------------------------------------------------

    def _update_section(self, content: str, section_title: str, new_text: str) -> str:
        """Replace the content of a section (## heading) with new_text.

        The section ends at the next ## heading or end of file.
        """
        lines = content.split("\n")
        start_idx = None
        end_idx = len(lines)

        for i, line in enumerate(lines):
            if line.strip() == f"## {section_title}":
                start_idx = i
                continue
            if start_idx is not None and line.startswith("## "):
                end_idx = i
                break

        if start_idx is None:
            # Section not found, append at end
            content = content.rstrip("\n") + f"\n\n## {section_title}\n{new_text}\n"
            return content

        # Rebuild: keep header line, replace body
        new_lines = lines[:start_idx + 1] + ["", new_text.strip(), ""] + lines[end_idx:]
        return "\n".join(new_lines)

    # ------------------------------------------------------------------
    # Helper: get section content
    # ------------------------------------------------------------------

    def _get_section(self, content: str, section_title: str) -> str:
        """Extract the content of a ## section."""
        lines = content.split("\n")
        start_idx = None
        end_idx = len(lines)

        for i, line in enumerate(lines):
            if line.strip() == f"## {section_title}":
                start_idx = i
                continue
            if start_idx is not None and line.startswith("## "):
                end_idx = i
                break

        if start_idx is None:
            return ""

        section_lines = lines[start_idx + 1:end_idx]
        return "\n".join(section_lines).strip()

    # ------------------------------------------------------------------
    # 1. create_company_profile
    # ------------------------------------------------------------------

    def create_company_profile(
        self,
        ticker: str,
        name: str,
        market: str,
        sector: str,
        thesis: str = "",
    ) -> str:
        """Create a new company profile from template.

        Returns the file path.
        """
        today = date.today().isoformat()
        template = f"""# {name} ({ticker})

## 基本信息
- 市场: {market}
- 行业: {sector}
- 首次关注: {today}
- 当前持仓: 0股 @ 0

## 投资论点 (Thesis)
{thesis if thesis else "待填写"}

## 当前评分
| 维度 | 评分 | 趋势 |
|------|------|------|
| 盈利 | 0/5 | → |
| 健康 | 0/5 | → |
| 现金流 | 0/5 | → |
| 估值 | 0/5 | → |
| 成长 | 0/5 | → |
| 股东 | 0/5 | → |
| 战略 | 0/5 | → |

**总分:** 0/40 **等级:** F **信号:** REDUCE

## 历史变化
| 日期 | 事件 | 评分 | 关键变化 |
|------|------|------|---------|

## 复盘记录

## 关键指标追踪
| 指标 | 上期 | 本期 | 变化 |
|------|------|------|------|

## 风险因素

## 用户反思
"""
        path = self._company_path(ticker)
        self._write_markdown(path, template)
        return path

    # ------------------------------------------------------------------
    # 2. update_company_scores
    # ------------------------------------------------------------------

    def update_company_scores(
        self,
        ticker: str,
        scores: dict,
        event_date: str = None,
    ) -> None:
        """Update scores section, add history row, detect trends."""
        path = self._company_path(ticker)
        content = self._read_markdown(path)
        if not content:
            raise FileNotFoundError(f"未找到公司档案: {ticker}")

        if event_date is None:
            event_date = date.today().isoformat()

        normalized = _normalize_scores(scores)

        # Get previous scores for trend detection
        prev_scores = self._extract_current_scores(content)

        # 合并：保留已有评分，只更新传入的维度
        merged = dict(prev_scores)
        merged.update(normalized)

        # Build score lines with trends
        score_lines = []
        changes = []
        for dim in _DIM_ORDER:
            new_val = merged.get(dim, 0)
            old_val = prev_scores.get(dim, 0)
            if new_val > old_val:
                trend = "↑"
                changes.append(f"{dim}↑")
            elif new_val < old_val:
                trend = "↓"
                changes.append(f"{dim}↓")
            else:
                trend = "→"
            score_lines.append(f"| {dim} | {new_val}/5 | {trend} |")

        total = sum(merged.get(d, 0) for d in _DIM_ORDER)
        grade = _compute_grade(total)
        signal = _compute_signal(total, merged)

        score_section = "| 维度 | 评分 | 趋势 |\n"
        score_section += "|------|------|------|\n"
        score_section += "\n".join(score_lines)
        score_section += f"\n\n**总分:** {total}/40 **等级:** {grade} **信号:** {signal}"

        content = self._update_section(content, "当前评分", score_section)

        # Add history row
        changes_str = ", ".join(changes) if changes else "无变化"
        history_row = f"| {event_date} | 评分更新 | {total}/40 | {changes_str} |"

        # Find and append to history table
        content = self._append_to_table(
            content, "历史变化",
            ["日期", "事件", "评分", "关键变化"],
            [event_date, "评分更新", f"{total}/40", changes_str],
        )

        self._write_markdown(path, content)

    def _extract_current_scores(self, content: str) -> dict:
        """Extract current dimension scores from the profile."""
        scores = {}
        rows = self._parse_table(content, "当前评分")
        for row in rows:
            dim = row.get("维度", "")
            score_str = row.get("评分", "0/5")
            try:
                val = int(score_str.split("/")[0])
            except (ValueError, IndexError):
                val = 0
            if dim in _DIM_ORDER:
                scores[dim] = val
        return scores

    def _append_to_table(
        self,
        content: str,
        section_title: str,
        headers: List[str],
        cells: List[str],
    ) -> str:
        """Append a row to a table within a section."""
        lines = content.split("\n")
        section_start = None
        section_end = len(lines)

        for i, line in enumerate(lines):
            if line.strip() == f"## {section_title}":
                section_start = i
                continue
            if section_start is not None and line.startswith("## "):
                section_end = i
                break

        if section_start is None:
            return content

        # Find the last table row in this section
        last_row_idx = None
        for i in range(section_start, section_end):
            stripped = lines[i].strip()
            if stripped.startswith("|") and "---" not in stripped:
                # Check if this is a header or separator
                cells_in_line = [c.strip() for c in stripped.split("|") if c.strip()]
                if cells_in_line and cells_in_line != headers:
                    last_row_idx = i

        new_row = "| " + " | ".join(cells) + " |"

        if last_row_idx is not None:
            lines.insert(last_row_idx + 1, new_row)
        else:
            # Find the separator line and insert after it
            for i in range(section_start, section_end):
                if "---" in lines[i]:
                    lines.insert(i + 1, new_row)
                    break

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 3. update_company_financials
    # ------------------------------------------------------------------

    def update_company_financials(
        self,
        ticker: str,
        financials: dict,
        event_date: str = None,
    ) -> None:
        """Update key financial metrics table."""
        path = self._company_path(ticker)
        content = self._read_markdown(path)
        if not content:
            raise FileNotFoundError(f"未找到公司档案: {ticker}")

        if event_date is None:
            event_date = date.today().isoformat()

        # Get previous financials
        prev_financials = self._extract_financials(content)

        # Build new financials table
        metrics = ["营收", "净利", "ROE", "毛利率", "经营现金流", "自由现金流", "PE", "负债率"]
        rows = []
        for metric in metrics:
            new_val = financials.get(metric, "")
            old_val = prev_financials.get(metric, "")
            if new_val == "":
                new_val = old_val if old_val else "-"
            if old_val == "" or old_val == "-":
                change = "-"
            else:
                try:
                    old_f = float(old_val)
                    new_f = float(new_val)
                    if old_f != 0:
                        pct = (new_f - old_f) / abs(old_f) * 100
                        if pct > 0:
                            change = f"+{pct:.1f}%"
                        elif pct < 0:
                            change = f"{pct:.1f}%"
                        else:
                            change = "持平"
                    else:
                        change = "-"
                except (ValueError, TypeError):
                    change = "-"
            rows.append([metric, str(old_val) if old_val else "-", str(new_val), change])

        table_text = self._format_table(
            ["指标", "上期", "本期", "变化"],
            rows,
        )
        content = self._update_section(content, "关键指标追踪", table_text)
        self._write_markdown(path, content)

    def _extract_financials(self, content: str) -> dict:
        """Extract current financial metrics."""
        rows = self._parse_table(content, "关键指标追踪")
        result = {}
        for row in rows:
            metric = row.get("指标", "")
            val = row.get("本期", "-")
            if val and val != "-":
                result[metric] = val
        return result

    # ------------------------------------------------------------------
    # 4. add_review
    # ------------------------------------------------------------------

    def add_review(
        self,
        ticker: str,
        review_text: str,
        event_date: str = None,
    ) -> None:
        """Add a review entry under 复盘记录."""
        path = self._company_path(ticker)
        content = self._read_markdown(path)
        if not content:
            raise FileNotFoundError(f"未找到公司档案: {ticker}")

        if event_date is None:
            event_date = date.today().isoformat()

        entry = f"\n### {event_date}\n{review_text}\n"

        # Find 复盘记录 section and append
        lines = content.split("\n")
        section_start = None
        section_end = len(lines)

        for i, line in enumerate(lines):
            if line.strip() == "## 复盘记录":
                section_start = i
                continue
            if section_start is not None and line.startswith("## "):
                section_end = i
                break

        if section_start is not None:
            # Insert before the next section
            lines = lines[:section_end] + [entry.rstrip("\n"), ""] + lines[section_end:]
            content = "\n".join(lines)
        else:
            content = content.rstrip("\n") + f"\n\n## 复盘记录\n{entry}\n"

        self._write_markdown(path, content)

    # ------------------------------------------------------------------
    # 5. add_thesis
    # ------------------------------------------------------------------

    def add_thesis(self, ticker: str, thesis: str) -> None:
        """Update the investment thesis section."""
        path = self._company_path(ticker)
        content = self._read_markdown(path)
        if not content:
            raise FileNotFoundError(f"未找到公司档案: {ticker}")

        content = self._update_section(content, "投资论点 (Thesis)", thesis)
        self._write_markdown(path, content)

    # ------------------------------------------------------------------
    # 6. add_risk
    # ------------------------------------------------------------------

    def add_risk(self, ticker: str, risk: str) -> None:
        """Add a risk factor."""
        path = self._company_path(ticker)
        content = self._read_markdown(path)
        if not content:
            raise FileNotFoundError(f"未找到公司档案: {ticker}")

        # Find 风险因素 section
        section_content = self._get_section(content, "风险因素")
        new_entry = f"- {risk}"
        if section_content:
            new_section = section_content + "\n" + new_entry
        else:
            new_section = new_entry

        content = self._update_section(content, "风险因素", new_section)
        self._write_markdown(path, content)

    # ------------------------------------------------------------------
    # 7. add_reflection
    # ------------------------------------------------------------------

    def add_reflection(self, ticker: str, reflection: str) -> None:
        """Add user reflection."""
        path = self._company_path(ticker)
        content = self._read_markdown(path)
        if not content:
            raise FileNotFoundError(f"未找到公司档案: {ticker}")

        section_content = self._get_section(content, "用户反思")
        today = date.today().isoformat()
        if section_content and section_content != "待填写":
            new_section = section_content + f"\n\n[{today}] {reflection}"
        else:
            new_section = f"[{today}] {reflection}"

        content = self._update_section(content, "用户反思", new_section)
        self._write_markdown(path, content)

    # ------------------------------------------------------------------
    # 8. get_company_profile
    # ------------------------------------------------------------------

    def get_company_profile(self, ticker: str) -> dict:
        """Read and parse the company markdown file.

        Returns structured dict with all sections.
        """
        path = self._company_path(ticker)
        content = self._read_markdown(path)
        if not content:
            raise FileNotFoundError(f"未找到公司档案: {ticker}")

        # Parse title
        title_match = re.search(r"^# (.+?) \((.+?)\)", content, re.MULTILINE)
        name = title_match.group(1) if title_match else ticker
        parsed_ticker = title_match.group(2) if title_match else ticker

        # Parse basic info
        basic_info = self._get_section(content, "基本信息")
        market = ""
        sector = ""
        first_follow = ""
        holding = ""
        for line in basic_info.split("\n"):
            line = line.strip()
            if line.startswith("- 市场:"):
                market = line.split(":", 1)[1].strip()
            elif line.startswith("- 行业:"):
                sector = line.split(":", 1)[1].strip()
            elif line.startswith("- 首次关注:"):
                first_follow = line.split(":", 1)[1].strip()
            elif line.startswith("- 当前持仓:"):
                holding = line.split(":", 1)[1].strip()

        # Parse thesis
        thesis = self._get_section(content, "投资论点 (Thesis)")

        # Parse scores
        score_rows = self._parse_table(content, "当前评分")
        scores = {}
        for row in score_rows:
            dim = row.get("维度", "")
            score_str = row.get("评分", "0/5")
            trend = row.get("趋势", "→")
            try:
                val = int(score_str.split("/")[0])
            except (ValueError, IndexError):
                val = 0
            scores[dim] = {"score": val, "trend": trend}

        # Parse total/grade/signal
        total_match = re.search(r"\*\*总分:\*\*\s*(\d+)/40", content)
        grade_match = re.search(r"\*\*等级:\*\*\s*(\w)", content)
        signal_match = re.search(r"\*\*信号:\*\*\s*(\w+)", content)
        total = int(total_match.group(1)) if total_match else 0
        grade = grade_match.group(1) if grade_match else "F"
        signal = signal_match.group(1) if signal_match else "REDUCE"

        # Parse history
        history = self._parse_table(content, "历史变化")

        # Parse reviews
        review_section = self._get_section(content, "复盘记录")
        reviews = []
        current_review = None
        for line in review_section.split("\n"):
            if line.startswith("### "):
                if current_review:
                    reviews.append(current_review)
                current_review = {"date": line[4:].strip(), "content": ""}
            elif current_review is not None:
                if current_review["content"]:
                    current_review["content"] += "\n" + line
                else:
                    current_review["content"] = line
        if current_review:
            reviews.append(current_review)

        # Parse financials
        financials = self._parse_table(content, "关键指标追踪")

        # Parse risks
        risk_section = self._get_section(content, "风险因素")
        risks = []
        for line in risk_section.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                risks.append(line[2:])

        # Parse reflections
        reflection = self._get_section(content, "用户反思")

        return {
            "ticker": parsed_ticker,
            "name": name,
            "market": market,
            "sector": sector,
            "first_follow": first_follow,
            "holding": holding,
            "thesis": thesis,
            "scores": scores,
            "total": total,
            "grade": grade,
            "signal": signal,
            "history": history,
            "reviews": reviews,
            "financials": financials,
            "risks": risks,
            "reflection": reflection,
        }

    # ------------------------------------------------------------------
    # 9. list_companies
    # ------------------------------------------------------------------

    def list_companies(self) -> List[dict]:
        """List all company profiles with ticker, name, latest score, latest date."""
        companies = []
        if not os.path.exists(self.companies_dir):
            return companies

        for fname in sorted(os.listdir(self.companies_dir)):
            if not fname.endswith(".md"):
                continue
            ticker = fname[:-3]  # strip .md
            try:
                profile = self.get_company_profile(ticker)
                companies.append({
                    "ticker": profile["ticker"],
                    "name": profile["name"],
                    "total": profile["total"],
                    "grade": profile["grade"],
                    "signal": profile["signal"],
                })
            except (FileNotFoundError, Exception):
                continue

        return companies

    # ------------------------------------------------------------------
    # 10. add_lesson
    # ------------------------------------------------------------------

    VALID_CATEGORIES = ["估值", "现金流", "增长", "风险管理", "心理", "其他"]

    def add_lesson(
        self,
        lesson: str,
        source_ticker: str = "",
        category: str = "",
    ) -> None:
        """Add a lesson to lessons.md."""
        if category and category not in self.VALID_CATEGORIES:
            category = "其他"

        content = self._read_markdown(self.lessons_path)
        today = date.today().isoformat()

        # Determine lesson number
        existing = re.findall(r"^### 经验 #\d+", content, re.MULTILINE)
        next_num = len(existing) + 1

        entry = f"\n### 经验 #{next_num}\n"
        entry += f"- **日期:** {today}\n"
        if source_ticker:
            entry += f"- **来源:** {source_ticker}\n"
        if category:
            entry += f"- **类别:** {category}\n"
        entry += f"- **内容:** {lesson}\n"

        content = content.rstrip("\n") + entry + "\n"
        self._write_markdown(self.lessons_path, content)

    # ------------------------------------------------------------------
    # 11. get_lessons
    # ------------------------------------------------------------------

    def get_lessons(self, category: str = None) -> List[dict]:
        """Read lessons, optionally filtered by category."""
        content = self._read_markdown(self.lessons_path)
        if not content:
            return []

        lessons = []
        # Split by ### headers
        blocks = re.split(r"(?=^### 经验 #\d+)", content, flags=re.MULTILINE)

        for block in blocks:
            if not block.strip().startswith("### 经验 #"):
                continue

            lesson = {"date": "", "source": "", "category": "", "content": ""}
            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("- **日期:**"):
                    lesson["date"] = line.split(":", 1)[1].strip().replace("**", "").strip()
                elif line.startswith("- **来源:**"):
                    lesson["source"] = line.split(":", 1)[1].strip().replace("**", "").strip()
                elif line.startswith("- **类别:**"):
                    lesson["category"] = line.split(":", 1)[1].strip().replace("**", "").strip()
                elif line.startswith("- **内容:**"):
                    lesson["content"] = line.split(":", 1)[1].strip().replace("**", "").strip()

            if category is None or lesson["category"] == category:
                lessons.append(lesson)

        return lessons

    # ------------------------------------------------------------------
    # 12. add_principle
    # ------------------------------------------------------------------

    def add_principle(self, principle: str, evidence: str = "") -> None:
        """Add an investment principle to principles.md."""
        content = self._read_markdown(self.principles_path)
        today = date.today().isoformat()

        existing = re.findall(r"^### 原则 #\d+", content, re.MULTILINE)
        next_num = len(existing) + 1

        entry = f"\n### 原则 #{next_num}\n"
        entry += f"- **日期:** {today}\n"
        entry += f"- **原则:** {principle}\n"
        if evidence:
            entry += f"- **依据:** {evidence}\n"

        content = content.rstrip("\n") + entry + "\n"
        self._write_markdown(self.principles_path, content)

    # ------------------------------------------------------------------
    # 13. get_principles
    # ------------------------------------------------------------------

    def get_principles(self) -> List[dict]:
        """Read all principles."""
        content = self._read_markdown(self.principles_path)
        if not content:
            return []

        principles = []
        blocks = re.split(r"(?=^### 原则 #\d+)", content, flags=re.MULTILINE)

        for block in blocks:
            if not block.strip().startswith("### 原则 #"):
                continue

            principle = {"date": "", "principle": "", "evidence": ""}
            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("- **日期:**"):
                    principle["date"] = line.split(":", 1)[1].strip().replace("**", "").strip()
                elif line.startswith("- **原则:**"):
                    principle["principle"] = line.split(":", 1)[1].strip().replace("**", "").strip()
                elif line.startswith("- **依据:**"):
                    principle["evidence"] = line.split(":", 1)[1].strip().replace("**", "").strip()

            principles.append(principle)

        return principles

    # ------------------------------------------------------------------
    # 14. add_journal_entry
    # ------------------------------------------------------------------

    def add_journal_entry(
        self,
        ticker: str,
        action: str,
        reason: str,
        event_date: str = None,
    ) -> None:
        """Add entry to the global decision journal."""
        content = self._read_markdown(self.journal_path)
        if event_date is None:
            event_date = date.today().isoformat()

        # Try to get current scores for the company
        scores_str = ""
        try:
            profile = self.get_company_profile(ticker)
            scores_str = f"{profile['total']}/40 ({profile['grade']}, {profile['signal']})"
        except FileNotFoundError:
            scores_str = "无数据"

        # Build journal entry
        entry = f"\n### {event_date} - {ticker}\n"
        entry += f"- **操作:** {action}\n"
        entry += f"- **原因:** {reason}\n"
        entry += f"- **当前评分:** {scores_str}\n"

        content = content.rstrip("\n") + entry + "\n"
        self._write_markdown(self.journal_path, content)

    # ------------------------------------------------------------------
    # 15. get_journal
    # ------------------------------------------------------------------

    def get_journal(self, ticker: str = None) -> List[dict]:
        """Read journal entries, optionally filtered by ticker."""
        content = self._read_markdown(self.journal_path)
        if not content:
            return []

        entries = []
        blocks = re.split(r"(?=^### \d{4}-\d{2}-\d{2})", content, flags=re.MULTILINE)

        for block in blocks:
            if not re.match(r"^### \d{4}-\d{2}-\d{2}", block.strip()):
                continue

            entry = {"date": "", "ticker": "", "action": "", "reason": "", "scores": ""}
            # Parse header line
            header_match = re.match(r"### (\d{4}-\d{2}-\d{2}) - (.+)", block.strip())
            if header_match:
                entry["date"] = header_match.group(1)
                entry["ticker"] = header_match.group(2).strip()

            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("- **操作:**"):
                    entry["action"] = line.split(":", 1)[1].strip().replace("**", "").strip()
                elif line.startswith("- **原因:**"):
                    entry["reason"] = line.split(":", 1)[1].strip().replace("**", "").strip()
                elif line.startswith("- **当前评分:**"):
                    entry["scores"] = line.split(":", 1)[1].strip().replace("**", "").strip()

            if ticker is None or entry["ticker"] == ticker:
                entries.append(entry)

        return entries

    # ------------------------------------------------------------------
    # 16. generate_company_summary
    # ------------------------------------------------------------------

    def generate_company_summary(self, ticker: str) -> str:
        """Generate a markdown summary suitable for inclusion in weekly report."""
        profile = self.get_company_profile(ticker)

        lines = []
        lines.append(f"## {profile['name']} ({ticker}) 周报摘要\n")
        lines.append(f"**市场:** {profile['market']}  **行业:** {profile['sector']}")
        lines.append(f"**持仓:** {profile['holding']}\n")

        # Current scores
        lines.append("### 当前评分")
        score_rows = []
        for dim in _DIM_ORDER:
            info = profile["scores"].get(dim, {"score": 0, "trend": "→"})
            score_rows.append([dim, f"{info['score']}/5", info.get("trend", "→")])
        lines.append(self._format_table(["维度", "评分", "趋势"], score_rows))
        lines.append(f"\n**总分:** {profile['total']}/40 **等级:** {profile['grade']} **信号:** {profile['signal']}\n")

        # Recent history (last 3)
        if profile["history"]:
            lines.append("### 近期变化")
            recent = profile["history"][-3:]
            hist_rows = []
            for h in recent:
                hist_rows.append([
                    h.get("日期", ""),
                    h.get("事件", ""),
                    h.get("评分", ""),
                    h.get("关键变化", ""),
                ])
            lines.append(self._format_table(["日期", "事件", "评分", "关键变化"], hist_rows))
            lines.append("")

        # Risk factors
        if profile["risks"]:
            lines.append("### 风险因素")
            for risk in profile["risks"]:
                lines.append(f"- ⚠️ {risk}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 17. generate_kb_summary
    # ------------------------------------------------------------------

    def generate_kb_summary(self) -> str:
        """Generate overview of entire knowledge base."""
        companies = self.list_companies()
        lessons = self.get_lessons()
        principles = self.get_principles()

        lines = []
        lines.append("# 意怠工程 - 知识库总览\n")

        # Companies
        lines.append(f"## 持仓公司 ({len(companies)}家)\n")
        if companies:
            comp_rows = []
            for c in companies:
                comp_rows.append([
                    c["ticker"],
                    c["name"],
                    f"{c['total']}/40",
                    c["grade"],
                    c["signal"],
                ])
            lines.append(self._format_table(
                ["代码", "名称", "总分", "等级", "信号"],
                comp_rows,
            ))
            lines.append("")

        # Lessons
        lines.append(f"## 经验教训 ({len(lessons)}条)\n")
        if lessons:
            # Group by category
            by_cat = {}
            for l in lessons:
                cat = l.get("category", "其他") or "其他"
                by_cat.setdefault(cat, []).append(l)
            for cat, cat_lessons in sorted(by_cat.items()):
                lines.append(f"### {cat} ({len(cat_lessons)}条)")
                for l in cat_lessons:
                    lines.append(f"- {l['content']}")
                lines.append("")

        # Principles
        lines.append(f"## 投资原则 ({len(principles)}条)\n")
        for p in principles:
            lines.append(f"- {p['principle']}")
        lines.append("")

        return "\n".join(lines)
