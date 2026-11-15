# 📈 CryptoOps Sentinel — v0.4.1

**Market intelligence · Multi-asset live watchlist · Explainable spot movement · Analyst-standard charts · Paper portfolio · Dated crypto news**

A read-only cryptocurrency analyst portfolio project built using FastAPI, Streamlit, Plotly, Kraken public Spot market data, and a **fictional portfolio**. It never places trades, reads private balances, or requests exchange API keys.

> **Important:** Percent movements are historical price descriptions, not investment advice. Technical BUY/HOLD/SELL *bias* is a transparent indicator rule, not a calibrated probability or trading recommendation. Price/news proximity does not establish causation.

## Patch in v0.4.1 — dashboard startup import fix

- Fixes Python packaging: the `dashboard` package is now included in the built distribution rather than only `cryptoops`.
- Adds `PYTHONPATH=/app` in the container and the dashboard service to make `/app/dashboard` importable when Streamlit launches the script.
- Adds packaging regression tests for dashboard imports and Docker configuration.
- Does **not** alter financial calculations, news sources or demo portfolio data.
- If the dashboard still fails, check the **last line** of `docker compose logs --tail=120 dashboard`, which identifies the actual exception. The single `from dashboard.charts import ...` line alone does not prove the root cause.

## Features introduced in v0.4.0

- **Consistent live watchlist lookbacks**: select **1 hour, 4 hours, 24 hours, 7 days, 30 days, 90 days, 180 days or 365 days**. Each monitored coin shows its latest live USD quote, net price change (%) and observed intraperiod high–low range (%). A completed Kraken candle supplies the baseline; the baseline time and candle interval are always displayed. Cache OHLC for 120 seconds to limit exchange requests; the latest live quote continues refreshing around every 5 seconds.
- **Industry-standard price charts**: switch between **candlesticks, OHLC bars, line and area** with optional **trade volume, SMA20/SMA50 and RSI14**. When available, click points on Line/Area views to send dates into the historical news tab; every chart style also has a dedicated date picker.
- **Portfolio chart views**: donut / horizontal bars / treemap for allocations and equity curve / equity area / underwater drawdown for synthetic risk history.
- **Professional table labels**: friendly finance-column titles, USD/percent formatting, and an **always-visible column terminology explanation immediately below each table** (holdings, venue exposure, CEX/DEX allocation, stress scenarios, correlations, risk metrics, operations records, and signal components).
- **All prior capabilities retained**: live price feeds, news with GDELT / recent RSS backup, historical event study, 70-term glossary, risk metrics, simulated holdings, reporting, ingestion and API documentation.

## Windows / Docker Desktop setup

1. Start Docker Desktop and confirm `docker version` shows a **Server** section.
2. **Stop the previous version** in the directory that contains its `docker-compose.yml`:

```powershell
cd "$HOME\Downloads\cryptoops-sentinel-v0.3.1\cryptoops-sentinel"
docker compose down
```

3. Unzip `cryptoops-sentinel-v0.4.1.zip`. Open PowerShell in the new **inner** `cryptoops-sentinel` directory and run:

```powershell
cd "$HOME\Downloads\cryptoops-sentinel-v0.4.1\cryptoops-sentinel"
docker compose up --build -d
docker compose ps
```

**Dashboard:** http://localhost:8501  
**API/OpenAPI docs:** http://localhost:8000/docs  
**Health:** http://localhost:8000/health

The project uses the same Compose service names/ports as older releases. Do not run both at the same time. `docker compose down` normally preserves the named PostgreSQL volume. **Do not use `down -v`** unless you intentionally want to delete the associated database volume.

## Analyst workflow

1. **Live watchlist:** select the coins on the left, then choose a **Price movement lookback**. Watch cards refresh in place. Net change and intraperiod range are **different** statistics: a coin may swing up/down significantly yet have a near-zero net return. If the historical baseline cannot be verified, the live price stays visible and the percentage is explicitly marked unavailable.
2. **Market research:** choose an instrument and historical period. Toggle candlestick/OHLC/line/area; show volume, SMA and/or RSI below the chart. Click a Line/Area close or use the date picker to forward a UTC date to News & event study. Technical-bias scores remain purely descriptive.
3. **News & event study:** query recent crypto headlines or dated coverage. GDELT historical article coverage is roughly 90 days; its public service may throttle. Current publisher RSS feeds only back up recent news, never historical archives. View surrounding daily price changes without claiming that an article caused the change.
4. **Paper portfolio:** compare hypothetical holdings, view venue/asset concentration, switch between allocation chart types, run deterministic stress scenarios and calculate historical risk. After calculating risk, its chart view remains adjustable without re-fetching the analysis.
5. **Analyst glossary:** search educational terminology for meanings and key influencing factors. Table-specific explanations now appear directly under every table as well.

## Price movement definition, caveats and historical limits

**Net change (%)** = `(latest live spot price / reference completed close − 1) × 100`.

**Observed price range (%)** = `(maximum observed candle high − minimum observed candle low) / reference completed close × 100` (including the live quote). This is a high–low *range*, **not** standard-deviation volatility or a future price bound.

For the chosen trailing period, the reference is the most recent completed candle close **at or before** the start of the period. Because only completed candles are used, the reference may predate the exact cutoff by as much as the candle interval. We report its timestamp. A stale or missing reference yields "unavailable" rather than an estimated return.

Kraken public Spot REST OHLC provides at most 720 recent candles per interval; periods select an interval that fits within the coverage window: 15 min (1h/4h/24h), 60 min (7d), 240 min (30d/90d) and daily (180d/365d). The newest, unfinished candle is deliberately omitted. Longer history may be limited or temporarily unavailable for particular assets. Spot quotes stream over WebSocket where available; a rate-limited REST fallback is available if the stream has no fresh quote. Prices may be stale, missing or delayed.

Data sources: [Kraken REST documentation](https://docs.kraken.com/api/) and the [Kraken public OHLC specification](https://docs.kraken.com/api/docs/rest-api/get-ohlc-data/). No credentials required for public endpoints.

## Main API routes

```text
GET /health
GET /api/v1/assets
GET /api/v1/live?symbols=BTC,ETH,SOL
GET /api/v1/watchlist/performance?symbols=BTC,ETH,SOL&period=7d
GET /api/v1/markets/BTC/history?days=30
GET /api/v1/portfolio
GET /api/v1/portfolio/analytics?lookback_days=180
GET /api/v1/news?symbol=BTC
GET /api/v1/news?symbol=BTC&selected_date=2026-11-10
GET /api/v1/events/BTC?selected_date=2026-11-10
GET /api/v1/glossary
GET /api/v1/operations
GET /api/v1/report/daily
```

### Validate directly in PowerShell

```powershell
curl.exe "http://localhost:8000/health"
curl.exe "http://localhost:8000/api/v1/watchlist/performance?symbols=BTC,ETH&period=24h"
docker compose logs --tail=100 api
docker compose logs --tail=100 dashboard
```

### Edit synthetic holdings

`config/demo_portfolio.json` is read-only mounted into the API container, so adjusting hypothetical position quantities/costs does not require an image rebuild. These balances **are not exchange-connected**.

## Local development / tests

```bash
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q cryptoops dashboard
python -m uvicorn cryptoops.api:app --host 127.0.0.1 --port 8000
# Another shell:
python -m streamlit run dashboard/app.py
```

Without Docker the default database is SQLite. `ENABLE_KRAKEN_WS=0` disables WebSocket streaming if needed.

Tests mock exchange and news services. They validate formula and Plotly figure construction but are **not** a live dashboard/browser or Docker smoke test.

### Project layout

```text
cryptoops/price_movement.py   # Timeframe map and independently testable price movement calculations
cryptoops/api.py              # Read-only FastAPI; new watchlist performance endpoint and caching
cryptoops/market.py           # Kraken public REST adapter
cryptoops/live.py             # Kraken WebSocket ticker and stale data protection
cryptoops/portfolio_analytics.py
cryptoops/news.py
cryptoops/glossary.py
dashboard/app.py              # Streamlit UI
 dashboard/charts.py           # Reusable Plotly chart builders
 dashboard/tables.py           # Human-readable table labels and column definitions
tests/test_v04.py              # New feature tests
```

See `docs/RELEASE_0_4.md`, `docs/ARCHITECTURE.md` and `docs/PORTFOLIO_RISK.md` for details.

### Explicit limitations

No live execution, trading accounts, authenticated exchange data, genuine venue-specific balances, portfolio cash flow ledger, slippage/fees, derivative margin risk, audited forecasts, or verified news-to-price causal attribution. This remains a research and portfolio demonstration.

---

## Publish to GitHub

Create an empty GitHub repository, then from the project directory:

```bash
git init
git add .
git commit -m "feat: CryptoOps Sentinel v0.4 analyst-grade charts and configurable price movement"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cryptoops-sentinel.git
git push -u origin main
```

Do not commit `.env`, private credentials, local database files, or copied client data. The `.gitignore` and `.dockerignore` exclude common local artifacts.
