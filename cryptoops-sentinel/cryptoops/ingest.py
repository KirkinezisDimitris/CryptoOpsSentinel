"""Explicit, auditable one-shot ingestion of public ticker snapshots.

Usage: python -m cryptoops.ingest --once
"""

import argparse
import asyncio
from datetime import UTC, datetime

from cryptoops.market import KrakenClient
from cryptoops.storage import initialize_database, save_tickers


async def ingest_once() -> int:
    ticker_batch = await KrakenClient().overview()
    captured = datetime.now(UTC)
    initialize_database()
    return save_tickers(ticker_batch, captured_at=captured)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one Kraken ticker snapshot batch")
    parser.add_argument("--once", action="store_true", help="Store one snapshot batch")
    args = parser.parse_args()
    if not args.once:
        parser.error("Use --once (no background scheduler is implemented in v0.1)")
    count = asyncio.run(ingest_once())
    print(f"Saved {count} ticker snapshots to the configured database.")


if __name__ == "__main__":
    main()
