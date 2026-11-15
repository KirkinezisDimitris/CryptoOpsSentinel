CryptoOps Sentinel
Cryptocurrency market intelligence, paper-portfolio analytics, and risk monitoring.

A read-only analytics platform built to explore how trading operations teams monitor digital-asset markets, assess hypothetical portfolio exposure, and investigate market events. The project combines live public market data with transparent financial calculations and a browser-based dashboard.

Stack: Python · FastAPI · Streamlit · Plotly · PostgreSQL / SQLite · Docker · Pytest

Portfolio project, not a trading service. Prices come from public data sources. Holdings and performance are simulated. No trades are executed and no private exchange API credentials are required. Technical BUY/HOLD/SELL labels are rule-based signals—not forecasts or financial advice.

Preview
Add 2–3 screenshots captured from your running dashboard to docs/screenshots/ and replace these placeholders before sharing the repository with recruiters.

Live watchlist	Portfolio & risk
docs/screenshots/live-watchlist.png	docs/screenshots/portfolio-risk.png


What it does
Area	Capabilities
Live market watchlist	Track selected cryptocurrencies in USD, with adjustable lookbacks (1h to 365d), net price change, and observed high–low range.
Market research	Explore candlestick, OHLC, line and area charts, with volume, SMA20/SMA50, and RSI14 overlays.
Technical signal analysis	See an explainable, rule-based BUY/HOLD/SELL bias and the indicators contributing to it. The score is not a probability.
News & event study	Browse recent relevant crypto headlines and examine nearby market movements for selected historical dates.
Paper portfolio	Value hypothetical positions using market prices; analyze unrealized P&L, asset weights, CEX/DEX allocation, and venue concentration.
Risk analytics	Explore scenario stress tests, historical Value at Risk, Expected Shortfall, correlation, and drawdown on simulated holdings.
Analyst glossary	Search 70 financial and market-analysis terms, with explanations of table metrics below their respective tables.


Architecture
                Kraken public REST / WebSocket
                           |
               Market-data & analysis modules
                           |
  News providers ---> FastAPI backend ---> PostgreSQL / SQLite
                           |
                    Streamlit + Plotly
                           |
                      Web dashboard
Two ways to run: the complete local edition runs separate Docker services, while the Streamlit Community Cloud edition calls the application logic inside the Streamlit process and uses REST polling rather than a persistent WebSocket worker. The cloud demonstration does not provide persistent database hosting or continuous background monitoring.
Quick start
Option A — Streamlit Community Cloud
Use the GitHub repository's main branch and set the main file path to:
dashboard/cloud_app.py
If your repository files are nested under an additional cryptoops-sentinel/ directory, use cryptoops-sentinel/dashboard/cloud_app.py instead. See [STREAMLIT_DEPLOY.md](STREAMLIT_DEPLOY.md) for deployment notes.
Option B — Docker (full local edition)
Requirements: Docker Desktop or Docker Engine with Compose, and internet access for public market data.
git clone https://github.com/KirkinezisDimitris/CryptoOpsSentinel.git
cd CryptoOpsSentinel
# If the application files are in a nested cryptoops-sentinel/ folder, cd there.
docker compose up --build -d
Open the dashboard at http://localhost:8501 and API docs at http://localhost:8000/docs.

Stop the stack with docker compose down (without -v if you want to retain database volumes).
Option C — Local Python development
python -m venv .venv
# Activate the environment for your operating system.
python -m pip install -e '.[dev]'
python -m pytest -q
For the cloud-style UI, consult START-HERE.md and the Streamlit-specific entry point. Python 3.11+ is recommended.
How the analytics should be interpreted
- Net change (%) compares the latest available spot price with a completed historical candle close at or before the selected period's start. The displayed reference timestamp makes the comparison auditable.
- Observed range (%) measures the difference between the observed period high and low relative to the reference close. It is not statistical volatility.
- Portfolio P&L and allocations use fictional quantities, acquisition prices, and exchange labels. They do not represent authenticated exchange balances.
- Historical VaR and Expected Shortfall are backward-looking risk estimates, not maximum-loss guarantees. Historical portfolio curves represent a simulated fixed-holdings scenario rather than actual trading records.
- News around a price move provides research context, not proof that an article caused the move.

- For details, see [Portfolio risk methodology](docs/PORTFOLIO_RISK.md) and [Architecture](docs/ARCHITECTURE.md).
Data sources and limitations
- Market data: Kraken public APIs — public endpoint access without exchange credentials. Kraken OHLC history is limited to recent candles, so long lookbacks or certain symbols may not always be available.
- News: GDELT article search, with RSS fallback for recent headlines. Historical news coverage and API availability are limited; current RSS headlines are never represented as past coverage.
- Availability: live sources may throttle, delay, or fail. Missing data should be shown as unavailable, not manufactured.
- Trading: no live order execution, margin management, verified P&L reconciliation, exchange-account access, or audited trading strategy is provided.
Engineering practices
- Modular market adapters, finance calculations, API endpoints, and presentation components.
- Automated tests for indicators, market-data parsing, portfolio/risk calculations, API responses, and dashboard chart helpers.
- Defensive handling of stale prices, incomplete candles, and upstream news-service failures.
- Public-data-only operation; do not commit .env, passwords, API keys, or private datasets.
Run the test suite with:
python -m pytest -q
Project structure
cryptoops/             # Market ingestion, signals, financial analytics, API
 dashboard/            # Streamlit pages and Plotly chart/table helpers
 config/               # Fictional demo portfolio
 docs/                 # Architecture, methodology, release history
 tests/                # Automated regression tests
 docker-compose.yml    # Full local service stack
 requirements.txt      # Streamlit/cloud dependencies
Roadmap
- Simulated transaction ledger: fills, fees, realized P&L, and reconciliations.
- Strategy backtesting with transaction costs and out-of-sample evaluation.
- Stronger data-quality monitoring and operational incident reporting.
- More explicit comparisons of portfolio risk against simple benchmarks.
Version
v0.4.1 — Market research charts, configurable movement periods, portfolio/risk visualizations, and chart-import packaging fixes. Development changes are recorded in docs/RELEASE_0_4.md and docs/RELEASE_0_4_1.md.
CryptoOps Sentinel is an independent educational engineering project built to demonstrate financial-data processing, analytical reasoning, operational monitoring, and software design. It is not affiliated with Kraken or any publisher.
