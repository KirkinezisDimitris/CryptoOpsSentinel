"""Public markets and explicit demo portfolio settings."""

import os
from pathlib import Path

SUPPORTED_PAIRS: dict[str, str] = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "SOL": "SOLUSD",
    "XRP": "XRPUSD",
    "ADA": "ADAUSD",
    "DOGE": "XDGUSD",
    "LTC": "LTCUSD",
    "LINK": "LINKUSD",
    "DOT": "DOTUSD",
    "AVAX": "AVAXUSD",
}
SUPPORTED_INTERVALS = (15, 60, 240, 1440)
DEFAULT_DATABASE_URL = "sqlite:///./cryptoops.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
MAX_SNAPSHOT_AGE_SECONDS = int(os.getenv("MAX_SNAPSHOT_AGE_SECONDS", "900"))
PORTFOLIO_FILE = Path(__file__).resolve().parent.parent / "config" / "demo_portfolio.json"
