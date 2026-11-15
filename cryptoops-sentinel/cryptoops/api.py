"""Read-only public API. All trading portfolios are synthetic demo inputs."""

import asyncio
import os
from datetime import UTC, date, datetime
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

from cryptoops.analytics import summarize_candles
from cryptoops.price_movement import LOOKBACKS, assess_movement
from cryptoops.config import SUPPORTED_INTERVALS, SUPPORTED_PAIRS
from cryptoops.market import KrakenClient, MarketDataError
from cryptoops.news import NewsClient, NewsDataError
from cryptoops.live import LiveFeed
from cryptoops.signals import technical_bias
from cryptoops.glossary import GLOSSARY, METRIC_GUIDE
from cryptoops.events import event_window
from cryptoops.portfolio_analytics import InsufficientHistoryError, analyze_historical_risk
from cryptoops.reporting import render_daily_report
from cryptoops.risk import evaluate_portfolio, load_demo_portfolio
from cryptoops.storage import get_operations_status, initialize_database

Symbol = str
news_client = NewsClient()
live_feed = LiveFeed()
_fallback_quotes: dict[str, tuple[float, dict]] = {}
_fallback_lock = asyncio.Lock()

def check_symbol(symbol: str) -> str:
    if symbol not in SUPPORTED_PAIRS:
        raise HTTPException(status_code=422, detail=f"Supported symbols: {list(SUPPORTED_PAIRS)}")
    return symbol

def parse_symbols(raw: str) -> list[str]:
    symbols = list(dict.fromkeys(x.strip().upper() for x in raw.split(",") if x.strip()))
    if not symbols or len(symbols) > 10 or any(s not in SUPPORTED_PAIRS for s in symbols):
        raise HTTPException(status_code=422, detail="Choose 1–10 supported comma-separated symbols")
    return symbols


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    background = None
    if os.getenv("ENABLE_KRAKEN_WS", "1") == "1":
        background = asyncio.create_task(live_feed.run())
    try:
        yield
    finally:
        if background is not None:
            background.cancel()
            with suppress(asyncio.CancelledError):
                await background


app = FastAPI(
    title="CryptoOps Sentinel",
    version="0.4.0",
    description="Public market intelligence and risk monitoring for a DEMO portfolio. No orders.",
    lifespan=lifespan,
)


def get_market() -> KrakenClient:
    return KrakenClient()


MarketDependency = Annotated[KrakenClient, Depends(get_market)]


def safe_market_error(exc: MarketDataError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/")
def info() -> dict[str, str]:
    return {
        "service": "CryptoOps Sentinel",
        "version": "0.4.0",
        "mode": "LIVE PUBLIC MARKET DATA + SYNTHETIC PAPER PORTFOLIO",
        "openapi": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cryptoops-api"}


@app.get("/api/v1/markets")
async def markets(market: MarketDependency, symbols: str | None = None):
    try:
        tickers = await market.overview(parse_symbols(symbols)) if symbols else await market.overview()
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc
    return {"markets": tickers, "mode": "LIVE KRAKEN SPOT DATA"}


@app.get("/api/v1/markets/{symbol}/candles")
async def market_candles(
    symbol: Symbol,
    market: MarketDependency,
    interval: Annotated[int, Query(description="Candle interval in minutes")] = 60,
):
    check_symbol(symbol)
    if interval not in SUPPORTED_INTERVALS:
        raise HTTPException(status_code=422, detail="Supported intervals: 15, 60, 240, 1440")
    try:
        candles = await market.candles(symbol, interval)
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc
    summary = summarize_candles(candles, interval)
    return {
        "symbol": symbol,
        "source": "Kraken Spot closed OHLC candles",
        **summary,
        "technical_bias": technical_bias(summary),
    }


@app.get("/api/v1/markets/{symbol}/orderbook")
async def market_orderbook(
    symbol: Symbol,
    market: MarketDependency,
    depth: Annotated[int, Query(ge=1, le=25)] = 10,
):
    check_symbol(symbol)
    try:
        return await market.orderbook(symbol, depth)
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc


@app.get("/api/v1/portfolio")
async def portfolio(market: MarketDependency):
    try:
        tickers = await market.overview()
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc
    return evaluate_portfolio(load_demo_portfolio(), tickers)


@app.get("/api/v1/portfolio/analytics")
async def portfolio_historical_analytics(
    market: MarketDependency,
    lookback_days: Annotated[int, Query(ge=60, le=365)] = 180,
):
    """Backward-looking diagnostics; public completed 1-day Spot candles only."""
    try:
        tickers, *histories = await asyncio.gather(
            market.overview(),
            *(market.candles(symbol, interval=1440) for symbol in ("BTC", "ETH", "SOL")),
        )
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc
    paper = evaluate_portfolio(load_demo_portfolio(), tickers)
    try:
        result = analyze_historical_risk(
            paper["positions"],
            dict(zip(("BTC", "ETH", "SOL"), histories, strict=True)),
            paper["market_value_usd"],
            lookback_days=lookback_days,
        )
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "portfolio_mode": paper["mode"],
        "live_portfolio_market_value_usd": paper["market_value_usd"],
        "market_data_provider": "Kraken public Spot REST",
        **result,
    }


@app.get("/api/v1/operations")
def operations():
    return get_operations_status()


@app.get("/api/v1/report/daily")
async def daily_report(market: MarketDependency):
    try:
        tickers = await market.overview()
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc
    paper = evaluate_portfolio(load_demo_portfolio(), tickers)
    return render_daily_report(tickers, paper)


@app.get("/api/v1/assets")
def assets():
    return {"symbols": list(SUPPORTED_PAIRS), "currency": "USD",
            "default_watchlist": ["BTC", "ETH", "SOL"]}


@app.get("/api/v1/live")
async def live_quotes(market: MarketDependency, symbols: str = "BTC,ETH,SOL"):
    """Prefer Kraken WS stream; use bounded-cache REST snapshots if disconnected."""
    import time
    selected = parse_symbols(symbols)
    snapshot = live_feed.snapshot(selected)
    if snapshot["missing_symbols"]:
        missing = snapshot["missing_symbols"]
        async with _fallback_lock:
            now = time.monotonic()
            refresh = [s for s in missing if not (s in _fallback_quotes and
                       now - _fallback_quotes[s][0] < 15)]
            if refresh:
                fetched = await asyncio.gather(*(market.ticker(s) for s in refresh),
                                               return_exceptions=True)
                for symbol, result in zip(refresh, fetched, strict=True):
                    if isinstance(result, dict):
                        _fallback_quotes[symbol] = (time.monotonic(), result)
            for symbol in missing:
                quote = _fallback_quotes.get(symbol)
                if quote is not None and time.monotonic() - quote[0] < 20:
                    snapshot["quotes"].append(quote[1])
        snapshot["missing_symbols"] = [
            s for s in selected if s not in {q["symbol"] for q in snapshot["quotes"]}
        ]
    snapshot["quotes"].sort(key=lambda q: selected.index(q["symbol"]))
    return snapshot


# Completed historical OHLC is cached independently from the 5-second WS quote refresh.
# A lock per cache protects against simultaneous dashboard requests duplicating REST calls.
_movement_candles: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_movement_locks: dict[tuple[str, int], asyncio.Lock] = {}
_movement_cache_ttl_seconds = 120


async def movement_candles(market: KrakenClient, symbol: str, interval: int) -> list[dict]:
    import time
    key = (symbol, interval)
    lock = _movement_locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _movement_candles.get(key)
        if cached and time.monotonic() - cached[0] < _movement_cache_ttl_seconds:
            return cached[1]
        result = await market.candles(symbol, interval=interval)
        _movement_candles[key] = (time.monotonic(), result)
        return result


@app.get("/api/v1/watchlist/performance")
async def watchlist_performance(
    market: MarketDependency,
    symbols: str = "BTC,ETH,SOL",
    period: str = "24h",
):
    """One consistent lookback definition across WS/REST sourced live spot quotes."""
    if period not in LOOKBACKS:
        raise HTTPException(status_code=422, detail=f"Supported periods: {list(LOOKBACKS)}")
    snapshot = await live_quotes(market, symbols)
    interval = LOOKBACKS[period][1]
    now = datetime.now(UTC)

    async def enrich(quote: dict) -> dict:
        try:
            historical = await movement_candles(market, quote["symbol"], interval)
            movement = assess_movement(float(quote["price_usd"]), historical, period, now)
            return {**quote, "movement": movement, "movement_status": "available"}
        except (MarketDataError, ValueError, TypeError, KeyError) as exc:
            # An unavailable history must not erase a valid live price.
            return {**quote, "movement": None, "movement_status": "unavailable",
                    "movement_error": str(exc)}

    # Bounded parallelism to avoid issuing a burst of public OHLC requests.
    limiter = asyncio.Semaphore(3)

    async def bounded(quote: dict) -> dict:
        async with limiter:
            return await enrich(quote)

    snapshot["quotes"] = await asyncio.gather(*(bounded(quote) for quote in snapshot["quotes"]))
    snapshot["selected_period"] = period
    snapshot["periods_available"] = list(LOOKBACKS)
    snapshot["movement_definition"] = (
        "Net price change and observed high-low range over the selected trailing period. "
        "Uses a live last-trade quote and an earlier completed Kraken candle close; "
        "reference time and candle interval are shown per asset."
    )
    return snapshot


@app.get("/api/v1/markets/{symbol}/history")
async def market_history(
    symbol: Symbol, market: MarketDependency,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
):
    from datetime import UTC, datetime, timedelta
    check_symbol(symbol)
    interval = 15 if days == 1 else 60 if days <= 7 else 240 if days <= 90 else 1440
    try:
        candles = await market.candles(symbol, interval)
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc
    minimum = datetime.now(UTC) - timedelta(days=days)
    selected = [c for c in candles if datetime.fromisoformat(c["time"]) >= minimum]
    if len(selected) < 2:
        raise HTTPException(status_code=503, detail="Not enough completed candles for this window")
    summary = summarize_candles(selected, interval)
    return {"symbol": symbol, "days_requested": days, "range_utc": "trailing window",
            "source": "Kraken Spot completed candles", **summary,
            "technical_bias": technical_bias(summary),
            "data_limit": "Kraken provides only the most recent 720 OHLC candles per interval."}


@app.get("/api/v1/glossary")
def glossary(q: str = "", level: str = "All", category: str = "All"):
    data = [row for row in GLOSSARY if
            (level == "All" or row["level"] == level) and
            (category == "All" or row["category"] == category) and
            (not q or q.casefold() in " ".join(str(x) for x in row.values()).casefold())]
    return {"total": len(data), "terms": data, "metric_guide": METRIC_GUIDE,
            "levels": ["Beginner", "Intermediate"],
            "categories": sorted({r["category"] for r in GLOSSARY})}


@app.get("/api/v1/news")
async def latest_news(symbol: Symbol = "BTC", selected_date: date | None = None):
    check_symbol(symbol)
    try:
        return await news_client.search(symbol, target_date=selected_date)
    except NewsDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/events/{symbol}")
async def event_context(symbol: Symbol, selected_date: date, market: MarketDependency):
    check_symbol(symbol)
    from datetime import UTC, datetime, timedelta
    if selected_date > datetime.now(UTC).date() or selected_date < (datetime.now(UTC) - timedelta(days=700)).date():
        raise HTTPException(status_code=422, detail="Date outside supported recent daily OHLC data")
    try:
        candles = await market.candles(symbol, interval=1440)
    except MarketDataError as exc:
        raise safe_market_error(exc) from exc
    return {"symbol": symbol, **event_window(candles, selected_date)}
