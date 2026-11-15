"""All exchange tests use fixtures; CI never depends on exchange uptime."""

import asyncio

import httpx
import pytest

from cryptoops.market import KrakenClient, MarketDataError


TICKER = {
    "a": ["101", "1", "1"],
    "b": ["99", "1", "1"],
    "c": ["100", "0.1"],
    "v": ["12", "48"],
    "h": ["110", "120"],
    "l": ["90", "80"],
    "o": "95",
}


def fake_client(payload: dict):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_ticker_parsing_and_utc_open_label():
    async def exercise():
        async with fake_client({"error": [], "result": {"XXBTZUSD": TICKER}}) as client:
            ticker = await KrakenClient(client).ticker("BTC")
        assert ticker["price_usd"] == 100
        assert ticker["spread_pct"] == 2
        assert ticker["change_since_utc_open_pct"] == 5.263
        assert ticker["volume_base_24h"] == 48
        assert ticker["source"].startswith("Kraken")

    asyncio.run(exercise())


def test_reject_exchange_api_error():
    async def exercise():
        async with fake_client({"error": ["EGeneral:Temporary lockout"], "result": {}}) as client:
            with pytest.raises(MarketDataError):
                await KrakenClient(client).ticker("BTC")

    asyncio.run(exercise())


def test_reject_crossed_market():
    async def exercise():
        crossed = {**TICKER, "a": ["98"], "b": ["99"]}
        async with fake_client({"error": [], "result": {"XXBTZUSD": crossed}}) as client:
            with pytest.raises(MarketDataError):
                await KrakenClient(client).ticker("BTC")

    asyncio.run(exercise())


def test_ohlc_excludes_unfinished_candle():
    rows = [
        [1600000000, "100", "110", "90", "105", "104", "42", 100],
        [1600003600, "105", "115", "95", "112", "111", "18", 120],
        [1600007200, "112", "999", "10", "999", "999", "70", 200],
    ]

    async def exercise():
        async with fake_client({"error": [], "result": {"XXBTZUSD": rows, "last": 1}}) as client:
            candles = await KrakenClient(client).candles("BTC", 60)
        assert len(candles) == 2
        assert candles[-1]["close"] == 112
        assert all(c["close"] != 999 for c in candles)

    asyncio.run(exercise())


def test_depth_parsing():
    payload = {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "bids": [["99.1", "1", 100]],
                "asks": [["99.2", "2", 100]],
            }
        },
    }

    async def exercise():
        async with fake_client(payload) as client:
            result = await KrakenClient(client).orderbook("BTC", 10)
        assert result["bids"][0]["price"] == 99.1
        assert result["asks"][0]["quantity"] == 2

    asyncio.run(exercise())
