"""Kraken public WebSocket v2 ticker snapshots, with reconnection and freshness checks."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import websockets

from cryptoops.config import SUPPORTED_PAIRS

LOG = logging.getLogger(__name__)
WS_URL = "wss://ws.kraken.com/v2"


def parse_ticker_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Validated v2 ticker records; ignore status/ack/heartbeat frames."""
    if message.get("channel") != "ticker" or not isinstance(message.get("data"), list):
        return []
    records = []
    for item in message["data"]:
        try:
            market = str(item["symbol"])
            base, quote = market.split("/", 1)
            if quote != "USD" or base not in SUPPORTED_PAIRS:
                continue
            price, bid, ask = (float(item[k]) for k in ("last", "bid", "ask"))
            if min(price, bid, ask) <= 0 or ask < bid:
                continue
            timestamp = datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                continue
            change = item.get("change_pct")
            volume = item.get("volume")
            mid = (bid + ask) / 2
            records.append({
                "symbol": base, "market": market, "price_usd": price,
                "bid_usd": bid, "ask_usd": ask,
                "spread_pct": round((ask - bid) / mid * 100, 5),
                "change_24h_pct": float(change) if change is not None else None,
                "volume_base_24h": float(volume) if volume is not None else None,
                "exchange_timestamp_utc": timestamp.astimezone(UTC).isoformat(),
                "fetched_at_utc": datetime.now(UTC).isoformat(),
                "source": "Kraken Spot WebSocket v2 (public ticker)",
            })
        except (KeyError, ValueError, TypeError, OverflowError, ZeroDivisionError):
            continue
    return records


class LiveFeed:
    def __init__(self) -> None:
        self.latest_by_symbol: dict[str, dict[str, Any]] = {}
        self.connected = False
        self.last_error: str | None = None

    def snapshot(self, symbols: list[str], *, max_age_seconds: int = 45) -> dict[str, Any]:
        now = datetime.now(UTC)
        quotes = []
        for symbol in symbols:
            item = self.latest_by_symbol.get(symbol)
            if item is None:
                continue
            try:
                stamp = datetime.fromisoformat(item["fetched_at_utc"])
            except (ValueError, KeyError):
                continue
            if now - stamp <= timedelta(seconds=max_age_seconds):
                quotes.append(item)
        return {
            "quotes": quotes,
            "missing_symbols": [s for s in symbols if s not in {q["symbol"] for q in quotes}],
            "connected": self.connected,
            "source": "Kraken WebSocket v2; UI requests snapshot every 5 seconds",
            "as_of_utc": now.isoformat(),
            "note": "No price is displayed when the exchange data is missing or stale.",
        }

    async def run(self) -> None:
        """Reconnect continuously; cancellation on FastAPI shutdown stops it."""
        symbols = [f"{base}/USD" for base in SUPPORTED_PAIRS]
        while True:
            try:
                async with websockets.connect(WS_URL, open_timeout=12, ping_interval=20,
                                              ping_timeout=20, max_size=2**20) as ws:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "ticker", "symbol": symbols,
                                   "event_trigger": "trades", "snapshot": True},
                    }))
                    self.connected = True
                    self.last_error = None
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except (ValueError, TypeError):
                            continue
                        if isinstance(data, dict) and data.get("success") is False:
                            LOG.warning("Kraken ticker subscription rejected: %s", data.get("error"))
                            self.last_error = "Exchange subscription rejected; see API logs"
                        if isinstance(data, dict):
                            for quote in parse_ticker_message(data):
                                self.latest_by_symbol[quote["symbol"]] = quote
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, websockets.exceptions.WebSocketException) as exc:
                LOG.warning("Kraken WebSocket reconnecting: %s", exc)
                self.last_error = "Exchange WebSocket temporarily unavailable"
            finally:
                self.connected = False
            await asyncio.sleep(5)
