"""CryptoOps Sentinel v0.4.1: research dashboard, not a trading terminal."""
from __future__ import annotations

import os
import asyncio
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.charts import (ALLOCATION_STYLES, EQUITY_STYLES, PRICE_STYLES,
                              allocation_chart, equity_chart, price_chart)
from dashboard.tables import show_table

# Community Cloud executes the FastAPI ASGI app in-process (no Docker sidecar).
from cryptoops.api import app as asgi_app
from cryptoops.storage import initialize_database

initialize_database()

async def _asgi_get(path: str) -> dict:
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cryptoops.local", timeout=40) as client:
        response = await client.get(path)
        response.raise_for_status()
        return response.json()


def internal_get(path: str) -> dict:
    return asyncio.run(_asgi_get(path))
PERIODS = {"24 hours": 1, "7 days": 7, "30 days": 30, "90 days": 90,
           "180 days": 180, "365 days": 365}

st.set_page_config(page_title="CryptoOps Sentinel | Community Demo", page_icon="📈", layout="wide")
st.title("📈 CryptoOps Sentinel | Community Demo")
st.caption("Market intelligence · Live watchlist · Historical news · Paper risk · Analyst learning")
st.warning("Research and education only. Prices are from Kraken; holdings are fictional. "
           "BUY/HOLD/SELL labels indicate a technical heuristic, NOT financial advice or probabilities.")


@st.cache_data(ttl=45, show_spinner=False)
def fetch(path: str) -> dict:
    return internal_get(path)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_news(path: str) -> dict:
    return internal_get(path)


def fetch_live(path: str) -> dict:
    # No Streamlit cache. The API itself caches REST fallback for a maximum of 15s.
    return internal_get(path)


def safe_fetch(path: str, *, news: bool = False) -> dict | None:
    try:
        return (fetch_news if news else fetch)(path)
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Data unavailable: {exc}")
        return None


def metric_info(guide: dict, *names: str) -> None:
    with st.expander("📚 What do these metrics mean and what affects them?"):
        for name in names:
            if name not in guide:
                continue
            item = guide[name]
            st.markdown(f"**{name}** — {item['meaning']}")
            st.caption(f"Affected by: {item['influences']}  |  Caution: {item['caution']}")


def list_news(data: dict | None) -> None:
    if not data:
        return
    st.caption(f"Source: {data.get('provider', 'unavailable')}")
    if data.get("fallback_used"):
        st.warning("Primary news source unavailable. Backup publisher feeds are in use where possible.")
    st.caption(data.get("note", ""))
    if not data.get("coverage_available", False):
        st.warning("News coverage unavailable for this request. This does not mean no news occurred.")
        return
    items = data.get("articles", [])
    if not items:
        st.info("No matching indexed headlines were returned. This is not proof that no relevant event happened.")
    for item in items:
        with st.container(border=True):
            st.markdown(f"**{item['title']}**")
            st.caption(f"{item['source'] if 'source' in item else item['domain']} · "
                       f"{item.get('time_kind', 'Observed')}: {item.get('observed_at_utc') or 'unknown'} · "
                       f"Headline relevance: {item['headline_relevance_score_pct']}%")
            st.caption(" · ".join(item["categories"]))
            st.link_button("Read original article ↗", item["url"])


assets = safe_fetch("/api/v1/assets")
all_symbols = assets.get("symbols", ["BTC", "ETH", "SOL"]) if assets else ["BTC", "ETH", "SOL"]
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["BTC", "ETH", "SOL"]

with st.sidebar:
    st.subheader("📡 Watchlist")
    watch = st.multiselect("Coins to monitor", all_symbols, key="watchlist", max_selections=10)
    if not watch:
        st.info("Choose at least one asset to activate the watchlist.")
    st.caption("Kraken USD Spot markets. Multi-select affects your dashboard session only.")
    st.markdown("**Coverage and provenance**")
    st.caption("Live: Kraken public REST quotes (periodically refreshed; not WebSocket streaming).")
    st.caption("Charts: closed Kraken candles. News: GDELT + publisher RSS backup, keyword ranking.")
    if st.button("↻ Refresh historical data"):
        fetch.clear()
        fetch_news.clear()
        st.rerun()
    st.caption("API endpoints run internally for the free-hosted demo; see repository for the Docker/API edition.")

watch_tab, research_tab, news_tab, portfolio_tab, glossary_tab, operations_tab = st.tabs([
    "📡 Live watchlist", "📈 Market research", "📰 News & event study",
    "💼 Paper portfolio", "📖 Analyst glossary", "🛠 Operations",
])

with watch_tab:
    st.subheader("Live exchange quotes & configurable price movement")
    st.caption("Kraken public REST spot quotes refresh when the dashboard updates; rate limits and latency apply. "
               "Historical comparisons use completed Kraken spot candles; no synthetic prices.")
    selected_window = st.selectbox(
        "Price movement lookback", ["1h", "4h", "24h", "7d", "30d", "90d", "180d", "365d"],
        index=2, key="live_movement_period",
        help="Trailing period measured from the current quote back to an earlier completed close.",
    )

    @st.fragment(run_every="5s")
    def live_panel(symbols: list[str], window: str):
        if not symbols:
            return
        try:
            snapshot = fetch_live(
                f"/api/v1/watchlist/performance?symbols={','.join(symbols)}&period={window}"
            )
        except (httpx.HTTPError, ValueError) as exc:
            st.error(f"Live market data unavailable: {exc}")
            return
        st.caption(f"REST snapshot (UTC): {snapshot['as_of_utc']} · REST is polled; no persistent WebSocket in free demo")
        if snapshot.get("missing_symbols"):
            st.warning(f"Unavailable / stale quotes: {', '.join(snapshot['missing_symbols'])}")
        quotes = snapshot.get("quotes", [])
        if not quotes:
            st.info("No fresh exchange quotes are currently available.")
            return
        columns = st.columns(min(3, len(quotes)))
        for idx, ticker in enumerate(quotes):
            with columns[idx % len(columns)]:
                movement = ticker.get("movement")
                delta = movement["change_pct"] if movement else None
                st.metric(
                    label=ticker["market"],
                    value=(f"${ticker['price_usd']:,.2f}" if ticker['price_usd'] >= 1
                           else f"${ticker['price_usd']:,.6f}"),
                    delta=f"{delta:+.2f}% over {window}" if delta is not None else None,
                )
                if movement:
                    st.caption(f"**{window} price range:** {movement['swing_pct']:.2f}% · "
                               f"High ${movement['observed_high_usd']:,.4f} · "
                               f"Low ${movement['observed_low_usd']:,.4f}")
                    st.caption(f"Comparison close: ${movement['reference_close_usd']:,.4f} "
                               f"at {movement['reference_close_time_utc']} "
                               f"({movement['ohlc_interval_minutes']}-min candles)")
                else:
                    st.caption(f"**{window} return:** unavailable — "
                               f"{ticker.get('movement_error', 'historical reference missing')}")
                source = "WebSocket" if "WebSocket" in ticker["source"] else "REST"
                st.caption(f"Bid–ask spread: {ticker['spread_pct']:.3f}% · {source} · "
                           f"Last observed: {ticker.get('exchange_timestamp_utc', ticker['fetched_at_utc'])}")
        st.markdown("**Live watchlist terminology**")
        st.caption(f"**Price change ({window})** is the net % movement from an earlier completed "
                   "candle close to the current spot quote. **Price range (%)** is the "
                   "highest observed high minus lowest observed low in the selected "
                   "period, divided by the reference close. A wide range can occur "
                   "even when the net return is close to zero. **Bid–ask spread (%)** "
                   "measures the gap between quoted buying/selling prices; it typically "
                   "widens when liquidity deteriorates or volatility rises. "
                   "Historical comparison times are approximate to the candle interval. "
                   "Unavailable comparisons are never replaced with made-up values.")

    live_panel(watch, selected_window)

with research_tab:
    st.subheader("Price chart, indicators & technical bias")
    if watch:
        left, right = st.columns([2, 1])
        with left:
            focus = st.selectbox("Focus asset", watch, key="focus_asset")
        with right:
            period = st.selectbox("Historical period", list(PERIODS), index=2)
        days = PERIODS[period]
        market = safe_fetch(f"/api/v1/markets/{focus}/history?days={days}")
        glossary_data = safe_fetch("/api/v1/glossary")
        guide = glossary_data["metric_guide"] if glossary_data else {}
        if market:
            df = pd.DataFrame(market["candles"])
            df["time"] = pd.to_datetime(df["time"], utc=True)
            latest = market["close_usd"]
            st.caption(f"Completed {market['interval_minutes']}-minute candles; last completed candle "
                       f"{df['time'].iloc[-1].isoformat()}. Live last trade may differ.")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Latest closed candle", f"${latest:,.4f}")
            m2.metric("RSI 14", "n/a" if market["rsi_14"] is None else f"{market['rsi_14']:.1f}")
            m3.metric("SMA20", "n/a" if market["sma_20_usd"] is None else f"${market['sma_20_usd']:,.4f}")
            m4.metric("SMA50", "n/a" if market["sma_50_usd"] is None else f"${market['sma_50_usd']:,.4f}")
            v1, v2, v3 = st.columns(3)
            v1.metric("Realized 24h volatility", "n/a" if market["realized_24h_vol_pct"] is None
                      else f"{market['realized_24h_vol_pct']:.2f}%")
            v2.metric("7-day close return", "n/a" if market["return_7d_pct"] is None
                      else f"{market['return_7d_pct']:+.2f}%")
            v3.metric("Maximum sample drawdown", f"{market['max_close_to_close_drawdown_pct']:.2f}%")
            bias = market["technical_bias"]
            if bias["score_pct"] is not None:
                st.progress(bias["score_pct"] / 100,
                            text=f"Directional technical bias: {bias['score_pct']}% — {bias['label'].replace('_', ' ')}")
                st.caption(bias["meaning"])
                with st.expander("See exact signal contributions"):
                    show_table(pd.DataFrame(bias["drivers"]), st)
                    st.json(bias["thresholds"])
            else:
                st.info(bias["meaning"])
            st.markdown("#### Interactive market chart")
            p1, p2 = st.columns([1, 2])
            with p1:
                chart_style = st.selectbox("Chart style", PRICE_STYLES, key="price_style",
                                           help="Standard analyst views: candlesticks, OHLC bars, close-price line and area.")
            with p2:
                overlays = st.multiselect("Chart studies", ["Volume", "Moving averages", "RSI (14)"],
                                          default=["Volume", "Moving averages"], key="chart_studies")
            fig = price_chart(df, focus, period, chart_style,
                              show_volume="Volume" in overlays,
                              show_rsi="RSI (14)" in overlays,
                              show_sma="Moving averages" in overlays)
            selection = st.plotly_chart(
                fig, key=f"chart_{focus}_{days}_{chart_style}",
                on_select="rerun", selection_mode="points", use_container_width=True,
            )
            # Click a close-price point (Line/Area). Candlesticks and OHLC may not
            # expose Plotly selection events in every Streamlit/Plotly combination.
            points = selection.selection.points if selection else []
            chosen = [p for p in points if p.get("x") and p.get("curve_number") == 0]
            if chosen:
                try:
                    selected_point_date = pd.to_datetime(chosen[-1]["x"], utc=True).date()
                    st.session_state["selected_event_date"] = selected_point_date
                    st.session_state[f"news_date_{focus}"] = selected_point_date
                    st.session_state["news_symbol"] = focus
                    st.caption(f"Selected {selected_point_date} for historical news review.")
                except (ValueError, TypeError):
                    pass
            st.caption("**Chart terminology:** **Candles/OHLC** show open, highest, lowest and "
                       "closing trades for each completed time interval; **volume** is the "
                       "number of base-asset units traded; **SMA20/50** smooth the last "
                       "20/50 candle closes; **RSI14** summarizes recent momentum "
                       "(not a guarantee of reversal). Chart date selection: use "
                       "Line/Area to click a close, or select any date below.")
            date_bounds = (df["time"].iloc[0].date(), df["time"].iloc[-1].date())
            selected_date = st.date_input("Choose a chart date for historical news",
                                          value=date_bounds[1], min_value=date_bounds[0],
                                          max_value=date_bounds[1], key=f"chart_date_{focus}_{days}")
            if st.button("Send selected date to News & event study", key="send_chart_date"):
                st.session_state["selected_event_date"] = selected_date
                st.session_state[f"news_date_{focus}"] = selected_date
                st.session_state["news_symbol"] = focus
                st.success(f"{focus} / {selected_date} selected. Open the News & event study tab.")
            metric_info(guide, "RSI 14", "SMA20 / SMA50", "24h volatility",
                        "Directional bias %", "Max Drawdown")
            st.info("Technical bias uses SMA20/SMA50 and RSI14. It is NOT derived from news, "
                    "a machine-learning model, or an empirically calibrated success rate.")
        st.markdown("#### Compare watchlisted assets")
        st.caption("Each series is rebased to 100 at its first *completed* close. "
                   "It compares relative performance, not USD prices or a tradable portfolio.")
        if len(watch) > 1:
            comp = go.Figure()
            for symbol in watch:
                data = market if market and symbol == focus else safe_fetch(
                    f"/api/v1/markets/{symbol}/history?days={days}")
                if not data:
                    continue
                candles = pd.DataFrame(data["candles"])
                if candles.empty or candles["close"].iloc[0] <= 0:
                    continue
                comp.add_trace(go.Scatter(
                    x=pd.to_datetime(candles["time"], utc=True),
                    y=candles["close"] / float(candles["close"].iloc[0]) * 100,
                    name=symbol, mode="lines",
                ))
            comp.update_layout(title=f"Indexed watchlist returns · {period}",
                               yaxis_title="Index (first close = 100)", height=340)
            st.plotly_chart(comp, use_container_width=True)

with news_tab:
    st.subheader("📰 News likely to concern crypto markets")
    st.caption("Headlines are prioritized using named assets and risk-related keywords: "
               "regulation, macro, ETF flows, security incidents and market structure. "
               "This is NOT a verified causal-impact classifier.")
    chosen_news = st.selectbox("Asset for news research", watch or all_symbols, key="news_symbol")
    latest, historical = st.tabs(["Recent headlines", "Historical date ↔ market changes"])
    with latest:
        st.caption("Recent headlines from GDELT (48-hour search) or backup publisher RSS feeds. Providers may limit access.")
        if st.button("Load / refresh recent articles", key="latest_news"):
            st.session_state["show_latest"] = True
        if st.session_state.get("show_latest"):
            list_news(safe_fetch(f"/api/v1/news?symbol={chosen_news}", news=True))
    with historical:
        today = datetime.now(UTC).date()
        default_day = st.session_state.get("selected_event_date", today - timedelta(days=1))
        if not isinstance(default_day, date) or default_day > today:
            default_day = today - timedelta(days=1)
        picker_key = f"news_date_{chosen_news}"
        if picker_key not in st.session_state:
            st.session_state[picker_key] = default_day
        date_choice = st.date_input(
            "Inspect news around a UTC date (±1 day) — or click a point in Market research",
            max_value=today, min_value=today - timedelta(days=365),
            key=picker_key,
        )
        st.caption("GDELT article lists are limited to about 90 days. "
                   "The Kraken chart can cover up to 365 days; older headlines may be unavailable.")
        if st.button("Inspect historical news and price changes", type="primary"):
            st.session_state["event_request"] = (chosen_news, date_choice.isoformat())
        if st.session_state.get("event_request") == (chosen_news, date_choice.isoformat()):
            context = safe_fetch(f"/api/v1/events/{chosen_news}?selected_date={date_choice.isoformat()}")
            if context:
                a, b, c = st.columns(3)
                a.metric("Previous close → selected day", "n/a" if context["previous_to_selected_day_pct"] is None
                         else f"{context['previous_to_selected_day_pct']:+.2f}%")
                b.metric("Selected day → following day", "n/a" if context["selected_to_next_day_pct"] is None
                         else f"{context['selected_to_next_day_pct']:+.2f}%")
                c.metric("Selected date close", "n/a" if context["selected_completed_close_usd"] is None
                         else f"${context['selected_completed_close_usd']:,.4f}")
                st.caption(context["methodology"])
                window = context.get("surrounding_completed_daily_closes", [])
                if window:
                    around = pd.DataFrame(window)
                    around["date_utc"] = pd.to_datetime(around["date_utc"], utc=True)
                    event_fig = go.Figure()
                    event_fig.add_trace(go.Scatter(
                        x=around["date_utc"], y=around["completed_close_usd"],
                        mode="lines+markers", name=f"{chosen_news} daily close",
                    ))
                    event_fig.add_vline(x=pd.Timestamp(date_choice, tz="UTC").timestamp() * 1000,
                                        line_dash="dot",
                                        annotation_text="Selected UTC date")
                    event_fig.update_layout(
                        title="Completed daily closes around the news date (±3 days)",
                        yaxis_title="USD", height=300,
                    )
                    st.plotly_chart(event_fig, use_container_width=True)
            data = safe_fetch(f"/api/v1/news?symbol={chosen_news}&selected_date={date_choice.isoformat()}",
                              news=True)
            list_news(data)
            st.info("An article appearing near a market move does not prove it caused that move. "
                    "Check original publication time, other concurrent events, and market-wide returns.")
            start = (date_choice - timedelta(days=1)).isoformat()
            end = (date_choice + timedelta(days=2)).isoformat()
            st.link_button("Search additional dated coverage on Google News",
                           f"https://www.google.com/search?tbm=nws&q={quote(chosen_news + ' after:' + start + ' before:' + end)}")

with glossary_tab:
    st.subheader("📖 Analyst dictionary")
    st.caption("Beginner and intermediate terms, including what each metric means, "
               "what affects it and how not to misread it.")
    ref = safe_fetch("/api/v1/glossary")
    if ref:
        a, b, c = st.columns([2, 1, 1])
        with a:
            search = st.text_input("Search terminology", placeholder="e.g. funding, RSI, liquidity")
        with b:
            level = st.selectbox("Difficulty", ["All"] + ref["levels"])
        with c:
            category = st.selectbox("Category", ["All"] + ref["categories"])
        filtered = [entry for entry in ref["terms"] if
                    (level == "All" or entry["level"] == level) and
                    (category == "All" or entry["category"] == category) and
                    (search.casefold() in " ".join(entry.values()).casefold())]
        st.caption(f"{len(filtered)} of {ref['total']} glossary entries")
        for entry in filtered:
            with st.expander(f"{entry['term']} · {entry['level']} · {entry['category']}"):
                st.write(entry["definition"])
                st.markdown(f"**How to interpret:** {entry['how_to_interpret']}")
                st.markdown(f"**Affected by:** {entry['affected_by']}")

# Retain the v0.2 portfolio and operations sections below.

with portfolio_tab:
    st.subheader("Hypothetical holdings — not a connected exchange account")
    paper = safe_fetch("/api/v1/portfolio")
    if paper:
        value, pnl, status, concentration = st.columns(4)
        value.metric("Paper portfolio market value", f"${paper['market_value_usd']:,.2f}")
        pnl.metric(
            "Unrealized P&L",
            f"${paper['unrealized_pnl_usd']:+,.2f}",
            f"{paper['unrealized_pnl_pct']:+.2f}% vs synthetic cost",
        )
        status.metric("Illustrative risk policy", paper["risk_status"])
        concentration.metric(
            "Effective asset count (HHI)",
            f"{paper['diversification']['effective_number_of_assets']:.2f}",
        )
        guide_data = safe_fetch("/api/v1/glossary")
        if guide_data:
            metric_info(guide_data["metric_guide"], "HHI", "Historical VaR", "Expected Shortfall", "Max Drawdown")
        st.markdown("#### Hypothetical positions")
        show_table(pd.DataFrame(paper["positions"]), st,
                   note="Hypothetical quantities and costs; all assets are marked using Kraken Spot quotes, even when a different venue is labeled.")
        st.markdown("#### Allocation & diversification")
        allocation_view = st.selectbox("Allocation chart", ALLOCATION_STYLES, key="allocation_view")
        asset_df = pd.DataFrame(paper["by_asset"])
        st.plotly_chart(allocation_chart(asset_df, allocation_view), use_container_width=True)
        st.caption("**Allocation chart:** the share of paper-portfolio market value in each asset. "
                   "Weights fluctuate with spot prices even when quantities remain unchanged. "
                   "Donut emphasizes proportions; horizontal bars compare weights; "
                   "treemap emphasizes relative sizes.")
        st.markdown("##### Exposure by trading venue")
        show_table(pd.DataFrame(paper["by_venue"]), st,
                   note="Venue labels come from the fictional portfolio configuration; these are NOT connected exchange balances.")
        st.markdown("##### Centralized vs decentralized venues")
        show_table(pd.DataFrame(paper["by_venue_type"]), st,
                   note="CEX/DEX classification is descriptive. No wallets, custody or on-chain balances are verified.")
        st.info(
            f"Largest asset: {paper['diversification']['largest_asset']} "
            f"({paper['diversification']['largest_asset_weight_pct']:.2f}%). "
            "HHI effective count measures concentration, not correlation diversification."
        )
        st.markdown("#### Paper portfolio stress testing")
        st.caption("Illustrative simultaneous percentage shocks to current Kraken spot marks. "
                   "Not a price forecast or probability model.")
        stress_df = pd.DataFrame(paper["stress_scenarios"])
        show_table(stress_df, st, note="Scenarios are deterministic hypothetical shocks, not forecasts or loss probabilities.")
        st.markdown("#### Risk rules")
        if paper["alerts"]:
            for alert in paper["alerts"]:
                st.warning(f"{alert['code']}: {alert['message']}")
        else:
            st.success("No breaches of the configured demo limits at this snapshot.")
        st.markdown("#### Historical risk model")
        st.caption("Optional analysis based on Kraken completed daily candles and fictional, "
                   "unchanged holdings. Not actual account returns or a prediction.")
        lookback = st.selectbox("Historical sample (completed UTC daily candles)",
                                [90, 180, 365], index=1)
        if st.button("Calculate historical risk (fetch OHLC history)"):
            st.session_state["paper_historical_result"] = safe_fetch(
                f"/api/v1/portfolio/analytics?lookback_days={lookback}"
            )
            st.session_state["paper_historical_lookback"] = lookback
        if (st.session_state.get("paper_historical_lookback") == lookback
                and st.session_state.get("paper_historical_result")):
            historical = st.session_state["paper_historical_result"]
            if historical:
                cards = st.columns(4)
                cards[0].metric("Annualized historic volatility",
                                f"{historical['annualized_historical_volatility_pct']:.2f}%")
                cards[1].metric("Historical max drawdown",
                                f"{historical['historical_max_drawdown_pct']:.2f}%")
                cards[2].metric(
                    f"Daily historical VaR ({historical['confidence_pct']:.0f}%)",
                    f"${historical['daily_historical_var_usd']:,.2f}",
                )
                cards[3].metric("Daily historical Expected Shortfall",
                                f"${historical['daily_historical_expected_shortfall_usd']:,.2f}")
                history = pd.DataFrame(historical["history"])
                history["date_utc"] = pd.to_datetime(history["date_utc"], utc=True)
                historical_view = st.selectbox("Historical portfolio chart", EQUITY_STYLES,
                                               key="portfolio_chart_style")
                st.plotly_chart(equity_chart(history, historical_view), use_container_width=True)
                st.caption("**Equity curve** is the retrospective value of fixed fictional holdings, "
                           "not a record of actual trades. **Drawdown** measures the percentage "
                           "decline from an earlier peak; the underwater view shows the full "
                           "sequence of these declines. Fees and transfers are excluded.")
                st.markdown("**Historical return correlation across assets**")
                show_table(pd.DataFrame(historical["asset_correlations"]), st,
                           note="Correlations use synchronized daily percentage returns; correlations are sample-dependent and do not imply causation.")
                st.markdown("**Asset-level historical risk metrics**")
                show_table(pd.DataFrame(historical["asset_historical_metrics"]), st)
                with st.expander("Historical risk calculation methodology"):
                    st.write(historical["methodology"])
                    st.write("Available synchronized daily observations:",
                             historical["sample_daily_returns"])
        with st.expander("Risk policy & accounting caveats"):
            st.json(paper["risk_policy"])
            st.write(paper["accounting_note"])
            st.write(paper["price_provenance_note"])
            st.write(paper["diversification"]["interpretation"])

with operations_tab:
    st.subheader("Ingestion health")
    operations = safe_fetch("/api/v1/operations")
    if operations:
        col1, col2 = st.columns(2)
        col1.metric("Stored snapshot rows", operations["total_snapshot_records"])
        col2.metric("Snapshot ingestion", operations["overall_status"])
        show_table(pd.DataFrame(operations["latest_by_symbol"]), st,
                   note="This table describes stored ingestion snapshots, not necessarily the 5-second WebSocket quote feed.")
        st.info(operations["note"])
    st.subheader("Daily market & risk brief")
    report = safe_fetch("/api/v1/report/daily")
    if report:
        st.download_button(
            label="Download Markdown report",
            data=report["content_markdown"],
            file_name=report["filename"],
            mime="text/markdown",
        )
        with st.expander("Preview report"):
            st.markdown(report["content_markdown"])
