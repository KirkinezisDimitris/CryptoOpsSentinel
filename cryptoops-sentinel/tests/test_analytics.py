from datetime import UTC, datetime, timedelta

import pytest

from cryptoops.analytics import summarize_candles


def make_candles(prices: list[float]) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        {
            "time": (start + timedelta(hours=i)).isoformat(),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume_base": 10.0,
        }
        for i, close in enumerate(prices)
    ]


def test_rising_market_indicators_and_sample_size():
    data = summarize_candles(make_candles([float(x) for x in range(100, 300)]), 60)
    assert data["completed_candles"] == 200
    assert data["sma_20_usd"] == pytest.approx(289.5)
    assert data["sma_50_usd"] == pytest.approx(274.5)
    assert data["rsi_14"] == 100.0
    assert data["return_7d_pct"] > 0
    assert data["max_close_to_close_drawdown_pct"] == 0
    assert data["candles"][0]["sma_20"] is None


def test_flat_market_rsi_is_neutral_and_volatility_zero():
    data = summarize_candles(make_candles([100.0] * 190), 60)
    assert data["rsi_14"] == 50.0
    assert data["realized_24h_vol_pct"] == 0


def test_drawdown_uses_peak_to_trough_in_observed_sample():
    data = summarize_candles(make_candles([100, 120, 90, 110]), 60)
    assert data["max_close_to_close_drawdown_pct"] == -25.0
    assert data["return_7d_pct"] is None
    assert data["rsi_14"] is None


def test_invalid_input():
    with pytest.raises(ValueError):
        summarize_candles([], 60)
    with pytest.raises(ValueError):
        summarize_candles(make_candles([0.0]), 60)
