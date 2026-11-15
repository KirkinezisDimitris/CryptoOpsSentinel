# Release 0.4.0 — Market charting & analyst terminology

## Changelog

- Added `GET /api/v1/watchlist/performance` using per-asset live quotes and cached historical closed OHLC baselines. Periods: 1h/4h/24h/7d/30d/90d/180d/365d.
- Improved reporting: independent **net percent change** and **historical high-low range percent**, with observed highs/lows, baseline close, baseline timestamp, source/freshness and explicit missing-data cases. Uses a **single window method** across WebSocket and REST fallback.
- Built reusable Plotly price chart types: candlestick, OHLC, line, area, optional volumes, 20/50 moving averages and RSI14 subplots. Date research remains available via date picker regardless of chart type.
- Portfolio visualization options: donut, horizontal allocation bars, treemap, retrospective equity line + drawdown pane, equity area and underwater chart.
- Renamed UI-facing finance tables to conventional human-facing column headings with always-visible descriptions immediately below each table. Raw API field names remain backwards compatible.
- Historical risk analysis result retained while users switch its chart representation in the current session.
- Preserved 0.3.1 GDELT/RSS reliability improvements and all previously implemented risk, news, report and glossary features.

## Calculation details

A trailing-window reference uses the latest completed close with a close timestamp at/before the exact cutoff. Approximation is bounded by the chosen candle interval and actual reference time is displayed. With 15-minute OHLC, a one-hour lookback may reference a close up to ~15 minutes older than the exact target. Range includes highs/lows in subsequent completed candles plus the latest spot quote; these are distinct from an annualized standard deviation or a market forecast.

## Operating constraints

Kraken public REST candle coverage is bounded and the live historical comparisons are cached for 120 seconds for rate-limit protection. If the requested reference is missing or stale, the API returns an explicit per-coin unavailable status; this never blocks a valid live price. This demo remains read-only, educational and synthetic for portfolios.

## Test strategy

Existing v0.3.1 tests plus new deterministic v0.4 checks for each lookback duration, incomplete/stale data, consistent comparison math, FastAPI behavior, four price chart types, three portfolio allocation charts, three portfolio equity views and professional table labeling. All external market/news calls are mocked in tests.
