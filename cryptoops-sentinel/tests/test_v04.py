"""Deterministic v0.4 movement, chart, UI metadata and API coverage."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from cryptoops import api
from cryptoops.price_movement import LOOKBACKS, assess_movement
from dashboard.charts import (ALLOCATION_STYLES, EQUITY_STYLES, PRICE_STYLES,
                              allocation_chart, equity_chart, price_chart, rsi_14)
from dashboard.tables import present_table

NOW = datetime(2026, 11, 15, 12, 30, tzinfo=UTC)


def mock_bars(period: str, now=NOW, price=100.0):
    lookback, interval = LOOKBACKS[period]
    start = now - lookback - timedelta(minutes=interval * 2)
    count = int((now - start).total_seconds() // (interval * 60))
    return [
        {"time": (start + timedelta(minutes=interval * i)).isoformat(),
         "open": price, "high": price + 6, "low": price - 4, "close": price,
         "volume_base": 12.0, "sma_20": None, "sma_50": None}
        for i in range(count)
    ]


@pytest.mark.parametrize("window", list(LOOKBACKS))
def test_movement_all_windows_have_comparable_reference(window):
    # All windows measure live price relative to a completed candle close.
    result = assess_movement(110, mock_bars(window), window, NOW)
    assert result["change_pct"] == 10.0
    assert result["swing_pct"] == 14.0
    assert result["observed_high_usd"] == 110
    assert result["observed_low_usd"] == 96
    assert 0 <= result["reference_age_minutes"] <= result["ohlc_interval_minutes"]
    assert datetime.fromisoformat(result["reference_close_time_utc"]) <= NOW - LOOKBACKS[window][0]


def test_movement_requires_completed_candle_before_cutoff():
    bars = mock_bars("1h")
    late = [c for c in bars if datetime.fromisoformat(c["time"]) >= NOW - timedelta(minutes=40)]
    with pytest.raises(ValueError, match="No completed historical close"):
        assess_movement(110, late, "1h", NOW)


def test_movement_refuses_stale_reference_and_invalid_price():
    bars = mock_bars("1h")
    with pytest.raises(ValueError, match="too old"):
        assess_movement(110, [{**bars[0], "time": (NOW - timedelta(hours=3)).isoformat()}], "1h", NOW)
    with pytest.raises(ValueError, match="positive finite"):
        assess_movement(float("nan"), bars, "1h", NOW)
    with pytest.raises(ValueError, match="Unsupported"):
        assess_movement(110, bars, "1w", NOW)


def test_movement_not_equal_range_even_when_return_zero():
    data = assess_movement(100, mock_bars("4h"), "4h", NOW)
    assert data["change_pct"] == 0
    assert data["swing_pct"] > 0


def test_v04_watchlist_route_with_fake_live_quotes(monkeypatch):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    class FakeMarket:
        async def candles(self, symbol, interval):
            return mock_bars("1h", now=now)
    quote = {
        "symbol": "BTC", "market": "BTC/USD", "price_usd": 110.0,
        "spread_pct": 0.01, "source": "Kraken Spot WebSocket v2 (public ticker)",
        "fetched_at_utc": datetime.now(UTC).isoformat(),
    }
    monkeypatch.setattr(api.live_feed, "snapshot", lambda syms: {
        "quotes": [quote], "missing_symbols": [], "connected": True,
        "as_of_utc": now.isoformat(),
    })
    api._movement_candles.clear()
    api.app.dependency_overrides[api.get_market] = lambda: FakeMarket()
    try:
        client = TestClient(api.app)
        res = client.get("/api/v1/watchlist/performance?symbols=BTC&period=1h")
        assert res.status_code == 200, res.text
        row = res.json()["quotes"][0]
        assert row["movement_status"] == "available"
        assert row["movement"]["change_pct"] == 10
        assert res.json()["selected_period"] == "1h"
        assert client.get("/api/v1/watchlist/performance?period=bad").status_code == 422
    finally:
        api.app.dependency_overrides.clear()
        api._movement_candles.clear()


def test_watchlist_keeps_live_price_when_history_unavailable(monkeypatch):
    class BrokenMarket:
        async def candles(self, symbol, interval):
            raise ValueError("history missing")
    quote = {"symbol": "BTC", "price_usd": 110.0}
    monkeypatch.setattr(api.live_feed, "snapshot", lambda syms: {
        "quotes": [quote], "missing_symbols": [], "connected": True,
        "as_of_utc": datetime.now(UTC).isoformat(),
    })
    api._movement_candles.clear()
    api.app.dependency_overrides[api.get_market] = lambda: BrokenMarket()
    try:
        res = TestClient(api.app).get("/api/v1/watchlist/performance?symbols=BTC&period=1h")
        assert res.status_code == 200
        quote = res.json()["quotes"][0]
        assert quote["price_usd"] == 110
        assert quote["movement"] is None
        assert quote["movement_status"] == "unavailable"
    finally:
        api.app.dependency_overrides.clear()
        api._movement_candles.clear()


@pytest.mark.parametrize("style", PRICE_STYLES)
def test_standard_chart_styles_render_as_plotly_objects(style):
    frame = pd.DataFrame(mock_bars("4h"))
    fig = price_chart(frame, "BTC", "4 hours", style, show_volume=True,
                      show_rsi=True, show_sma=True)
    assert len(fig.data) >= 5
    assert fig.layout.yaxis.title.text == "Price (USD)"
    # Force full Plotly JSON validation, including multi-row candlesticks and RSI.
    assert 'BTC' in fig.to_json() and fig.layout.title.text.startswith('BTC/USD')


@pytest.mark.parametrize("style", ALLOCATION_STYLES)
def test_allocation_styles(style):
    frame = pd.DataFrame([
        {"symbol": "BTC", "weight_pct": 60, "market_value_usd": 600},
        {"symbol": "ETH", "weight_pct": 40, "market_value_usd": 400},
    ])
    fig = allocation_chart(frame, style)
    assert fig.data[0].type in ("pie", "bar", "treemap")
    assert "Asset allocation" in fig.to_json()


@pytest.mark.parametrize("style", EQUITY_STYLES)
def test_equity_views(style):
    history = pd.DataFrame([
        {"date_utc": "2026-11-13", "synthetic_buy_hold_value_usd": 1000, "drawdown_pct": 0},
        {"date_utc": "2026-11-14", "synthetic_buy_hold_value_usd": 900, "drawdown_pct": -10},
    ])
    fig = equity_chart(history, style)
    assert fig.data
    assert "fictional" in fig.to_json().lower()


def test_table_headers_clean_and_explanations_present():
    df = pd.DataFrame([{"symbol": "BTC", "venue": "Kraken", "unit_cost_usd": 30000,
                        "unrealized_pnl_pct": -10, "weight_pct": 100}])
    visible, terms = present_table(df)
    assert list(visible.columns) == ["Asset", "Trading Venue", "Entry Price (USD)",
                                     "Unrealized P&L (%)", "Portfolio Weight (%)"]
    assert len(terms) == 5
    assert all(meaning and driver for _, meaning, driver in terms)


def test_rsi_flat_is_neutral():
    values = pd.Series([100.0] * 18)
    assert rsi_14(values).iloc[-1] == 50
