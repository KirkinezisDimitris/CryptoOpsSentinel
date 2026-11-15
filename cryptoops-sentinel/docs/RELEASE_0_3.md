# CryptoOps Sentinel v0.3 — feature guide

## Why a research terminal instead of a trading bot?

The project demonstrates a junior financial-market analyst's workflow without needing credentials or putting funds at risk. All trading-related labels are illustrative and cannot place orders.

## Six tabs

| Tab | Use |
|---|---|
| Live watchlist | Choose 1–10 Kraken Spot USD markets; inspect a public WebSocket stream refreshed on screen every five seconds, with explicit REST fallback and quote freshness status |
| Market research | Pick asset and a 1/7/30/90/180/365-day window; inspect completed price candles, RSI, SMA, historical volatility, technical bias and normalized watchlist comparisons |
| News & event study | Inspect ranked headlines; from a selected chart point or date, retrieve nearby indexed headlines and compare the adjacent UTC completed closes |
| Paper portfolio | Retains v0.2 hypothetical P&L, CEX/DEX allocation, diversification, historical VaR/ES, correlated risk and synthetic buy/hold scenarios |
| Analyst glossary | Search and filter 60+ beginner/intermediate financial terms including what a metric means, what moves it and common interpretation mistakes |
| Operations | Inspect opt-in stored snapshots and download a daily Markdown market/risk brief |

## Live feed

`Kraken WebSocket v2 -> FastAPI cache -> /api/v1/live?symbols=BTC,ETH -> Streamlit fragment (every 5s)`

- WS data is exchange-originated and pushed to the backend. No API key.
- Backend removes quotes not updated within 45 seconds.
- Missing quotes use REST fallback cached 15 seconds, labeled accordingly.
- An empty/missing quote remains missing: no synthetic or forward-filled price.
- WS `change_24h_pct` is a *rolling* 24-hour change; REST `change_since_utc_open_pct` is *since UTC open*. These are not interchangeable.
- The UI display updates every five seconds. It does not show every trade and is not a low-latency trading terminal.
- The live watchlist only changes the user's current Streamlit session and is not written to the server.

## Technical bias rubric (explainable, not probabilistic)

A deterministic, symmetric 0–100 heuristic, with 50 neutral:

| Completed-candle rule | Positive | Negative |
|---|---:|---:|
| Latest close above/below SMA20 | +15 | -15 |
| SMA20 above/below SMA50 | +25 | -25 |
| RSI14 in (50,70] / [30,50); above 70 is overbought, below 30 potentially oversold | +10 in moderate positive momentum **or RSI below 30** | -10 in moderate negative momentum **or RSI above 70** |

- Score >=65 = `BUY_BIAS` (bullish technical stance)
- Score 36–64 = `HOLD_NEUTRAL`
- Score <=35 = `SELL_BIAS` (bearish technical stance)
- It **is not** a recommendation to trade, a probability of success, or a validated edge. No market maker costs, fees, news, leverage, forward returns, or transaction history are included. The countertrend RSI rule may misfire badly in strong trends.
- Undefined RSI/SMA results return `INSUFFICIENT_DATA`, never a fabricated score.

## Historical event study and limitations

1. Select a point on **Market research** (or explicitly select a UTC date in **News & event study**).
2. Switch to **News & event study → Historical date ↔ market changes**.
3. Click **Inspect historical news and price changes**.
4. Read headlines indexed near the chosen date (one-day margin) and descriptive previous/selected/next completed UTC daily closes.

**Interpretation:** GDELT `seendate` records when an article entered the index, not necessarily when it was originally published or when the underlying event occurred. Nearby news *does not imply cause*. Confounders include other news, ETF flows, liquidity and market-wide shocks.

**Limits:** GDELT public DOC 2.0 `ArtList` covers about the latest three months. Historical price candles may cover 365 days, but older headline lists will be marked unavailable. Even within 90 days, an empty news search only indicates no indexed matches for our query. GDELT also rate-limits the public API; search requests are cached for 10 minutes (recent) or one hour (dated), and paced to at most one every 5.5 seconds within a process. A direct Google News search link is provided as a research fallback, not an automated reliable archive.

## Documented risk analytics

See [PORTFOLIO_RISK.md](PORTFOLIO_RISK.md). v0.3 preserves the v0.2 hypothetical portfolio's current cost vs marks, position/venue weights, synthetic stress shocks and historical 95% daily historical VaR/Expected Shortfall. It has no broker/private-API connection and does not include a trade ledger or P&L from actual executions.

## Operational constraints

- The project uses a permissive demo PostgreSQL password in Docker Compose. **For local development only; do not expose these ports publicly**.
- Never paste personal exchange keys into this app. It contains no authenticated exchange code.
- Unit tests use mocks for market/news feeds and are reproducible offline.
- News feeds, live WS, and Streamlit UI were not integration-tested against the live Internet when packaged; verify these locally with the documented smoke tests.

## v0.3.1 hotfix

The recent-news provider now tries GDELT first, then publisher RSS feeds from CoinDesk and Cointelegraph if GDELT fails. This makes today's news view more robust when the public article-search service is unavailable or throttling. Source and time provenance are shown for each article. A fallback RSS `pubDate` is a publisher-provided publication timestamp, not a GDELT first-seen time. A failed GDELT request triggers a 10-minute cooldown to avoid aggressive retries.

The historical-date view intentionally **does not** replace missing historical GDELT results with today's publisher RSS. It shows an explicit unavailable state and continues to offer an external dated search link. Source failure is not proof there was no news.
