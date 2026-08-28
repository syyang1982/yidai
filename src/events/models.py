from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MarketEvent:
    event_id: str = ""
    event_type: str = ""        # earnings/product/regulatory/macro/breaking/ipo/dividend
    title: str = ""
    description: str = ""
    event_date: str = ""        # YYYY-MM-DD
    event_time: str = ""
    affected_tickers: List[str] = field(default_factory=list)
    sector: str = ""
    source: str = ""
    source_url: str = ""
    impact_level: str = ""      # high/medium/low
    impact_direction: str = ""  # positive/negative/neutral/unknown
    impact_analysis: str = ""
    status: str = "pending"     # pending/active/completed/expired
    notified: bool = False
    created_at: str = ""
    updated_at: str = ""
