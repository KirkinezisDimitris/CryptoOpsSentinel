"""Defensive, public-only Kraken Spot REST adapter.

No account, credentials, orders, wallet addresses or private API calls are used.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from cryptoops.config import SUPPORTED_INTERVALS, SUPPORTED_PAIRS

BASE_URL = "https://api.kraken.com/0/public"


class MarketDataError(Exception):
    """The upstream market feed returned an invalid or unavailable response."""


class KrakenClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        async def request(client: httpx.AsyncClient) -> dict[str, Any]:
            try:
                response = await client.get(f"{BASE_URL}/{endpoint}", params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MarketDataError(f"Kraken {endpoint} request failed") from exc
            if not isinstance(payload, dict) or payload.get("error"):
                raise MarketDataError(f"Kraken {endpoint} returned an API error")
            result = payload.get("result")
            if not isinstance(result, dict) or not result:
                raise MarketDataError(f"Kraken {endpoint} returned no market data")
            return result

        if self._client is not None:
            return await request(self._client)
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            return await request(client)

    async def ticker(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.upper()
        if symbol not in SUPPORTED_PAIRS:
            raise ValueError(f"Unsupported symbol: {symbol}")
        result = await self._get("Ticker", {"pair": SUPPORTED_PAIRS[symbol]})
        # Kraken returns its canonical pair key (e.g. XXBTZUSD), not necessarily our query key.
        item = next(iter(result.values()))
        try:
            price = float(item["c"][0])
            ask = float(item["a"][0])
            bid = float(item["b"][0])
            utc_open = float(item["o"])
            high_24h = float(item["h"][1])
            low_24h = float(item["l"][1])
            volume_base_24h = float(item["v"][1])
            if min(price, bid, ask, utc_open) <= 0 or ask < bid:
                raise ValueError("Nonpositive or crossed ticker prices")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MarketDataError(f"Kraken ticker has invalid fields for {symbol}") from exc
        mid = (ask + bid) / 2
        return {
            "symbol": symbol,
            "market": f"{symbol}/USD",
            "price_usd": price,
            "bid_usd": bid,
            "ask_usd": ask,
            "spread_pct": round((ask - bid) / mid * 100, 5),
            "utc_open_usd": utc_open,
            "change_since_utc_open_pct": round((price / utc_open - 1) * 100, 3),
            "high_24h_usd": high_24h,
            "low_24h_usd": low_24h,
            "volume_base_24h": volume_base_24h,
            "source": "Kraken Spot (public REST API)",
            "fetched_at_utc": datetime.now(UTC).isoformat(),
        }

    async def overview(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        targets = symbols if symbols is not None else ["BTC", "ETH", "SOL"]
        if not targets or any(symbol not in SUPPORTED_PAIRS for symbol in targets):
            raise ValueError("Invalid market symbols")
        return await asyncio.gather(*(self.ticker(symbol) for symbol in targets))

    async def candles(self, symbol: str, interval: int = 60) -> list[dict[str, Any]]:
        symbol = symbol.upper()
        if symbol not in SUPPORTED_PAIRS or interval not in SUPPORTED_INTERVALS:
            raise ValueError("Unsupported market symbol or candle interval")
        result = await self._get("OHLC", {"pair": SUPPORTED_PAIRS[symbol], "interval": interval})
        entries = next((rows for key, rows in result.items() if key != "last"), None)
        if not isinstance(entries, list) or len(entries) < 2:
            raise MarketDataError("Too few OHLC records")
        # Kraken's final OHLC row is the still-forming candle: never use it for analysis.
        completed = entries[:-1]
        candles: list[dict[str, Any]] = []
        try:
            for row in completed:
                candles.append(
                    {
                        "time": datetime.fromtimestamp(int(row[0]), tz=UTC).isoformat(),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume_base": float(row[6]),
                    }
                )
        except (IndexError, ValueError, TypeError, OverflowError) as exc:
            raise MarketDataError("Malformed OHLC candle") from exc
        if any(c["close"] <= 0 or c["high"] < c["low"] for c in candles):
            raise MarketDataError("Invalid OHLC prices")
        return candles

    async def orderbook(self, symbol: str, depth: int = 10) -> dict[str, Any]:
        symbol = symbol.upper()
        if symbol not in SUPPORTED_PAIRS:
            raise ValueError("Unsupported market symbol")
        if not 1 <= depth <= 25:
            raise ValueError("Depth must be between 1 and 25")
        result = await self._get("Depth", {"pair": SUPPORTED_PAIRS[symbol], "count": depth})
        book = next(iter(result.values()))
        try:
            bids = [{"price": float(x[0]), "quantity": float(x[1])} for x in book["bids"]]
            asks = [{"price": float(x[0]), "quantity": float(x[1])} for x in book["asks"]]
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise MarketDataError("Malformed orderbook") from exc
        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "source": "Kraken Spot order book",
            "fetched_at_utc": datetime.now(UTC).isoformat(),
        }
