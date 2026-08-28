"""Theme-to-ticker mapper for the 意怠工程 event engine.

Maps news text to portfolio tickers by matching keywords against
a curated theme database (theme_mapping.json).
"""

import json
from pathlib import Path
from typing import List, Optional


_MAPPER_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "events" / "theme_mapping.json"


class ThemeMapper:
    """Match news headlines / text to portfolio tickers via theme keywords."""

    def __init__(self, mapping_path: Optional[Path] = None):
        path = Path(mapping_path) if mapping_path else _MAPPER_PATH
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._themes: list[dict] = data["themes"]

    # ── public API ───────────────────────────────────────────────────

    def match_news_to_portfolio(self, news_text: str) -> List[dict]:
        """Return list of {ticker, theme, relation, confidence, keywords_matched}
        for every theme whose keywords appear in *news_text*.
        """
        results = []
        for theme in self._themes:
            matched = [kw for kw in theme["keywords"] if kw in news_text]
            if not matched:
                continue
            confidence = len(matched) / len(theme["keywords"])
            for entry in theme["affected_tickers"]:
                results.append({
                    "ticker": entry["ticker"],
                    "theme": theme["theme"],
                    "relation": entry["relation"],
                    "confidence": round(confidence, 3),
                    "keywords_matched": matched,
                })
        return results

    def get_theme_keywords(self, ticker: str) -> List[str]:
        """Return all keywords from themes that affect *ticker*."""
        keywords: list[str] = []
        seen: set[str] = set()
        for theme in self._themes:
            if any(t["ticker"] == ticker for t in theme["affected_tickers"]):
                for kw in theme["keywords"]:
                    if kw not in seen:
                        seen.add(kw)
                        keywords.append(kw)
        return keywords

    def find_related_themes(self, keywords: List[str]) -> List[dict]:
        """Return themes that contain at least one of *keywords*."""
        results = []
        kw_set = set(keywords)
        for theme in self._themes:
            overlap = kw_set & set(theme["keywords"])
            if overlap:
                results.append({
                    "theme": theme["theme"],
                    "priority": theme["priority"],
                    "matched_keywords": sorted(overlap),
                })
        return results

    def get_all_tickers(self) -> List[str]:
        """Return deduplicated list of all tickers across themes."""
        seen: set[str] = set()
        tickers: list[str] = []
        for theme in self._themes:
            for entry in theme["affected_tickers"]:
                t = entry["ticker"]
                if t not in seen:
                    seen.add(t)
                    tickers.append(t)
        return tickers
