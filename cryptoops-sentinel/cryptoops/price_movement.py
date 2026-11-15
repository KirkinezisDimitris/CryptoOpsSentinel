"""Auditable trailing-window spot movement, using live quotes and completed candles.

Unlike the WebSocket 24h delta and REST UTC-open delta, every result here uses
one consistent definition for each selected lookback window.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

# Period -> (lookback, Kraken OHLC interval in minutes). Respect Kraken 720-bar cap.
LOOKBACKS: dict[str, tuple[timedelta, int]] = {
    "1h": (timedelta(hours=1), 15),
    "4h": (timedelta(hours=4), 15),
    "24h": (timedelta(hours=24), 15),
    "7d": (timedelta(days=7), 60),
    "30d": (timedelta(days=30), 240),
    "90d": (timedelta(days=90), 240),
    "180d": (timedelta(days=180), 1440),
    "365d": (timedelta(days=365), 1440),
}


def assess_movement(
    current_price: float,
    candles: list[dict[str, Any]],
    period: str,
    now: datetime,
) -> dict[str, Any]:
    """Compare a live quote to the most recent completed close AT/before start.

    OHLC timestamps indicate candle *start*, so the close timestamp is start + interval.
    Selecting a prior completed candle avoids look-ahead. Returns both net change
    and observed high-low swing (not volatility / probability).
    """
    if period not in LOOKBACKS:
        raise ValueError("Unsupported lookback period")
    if now.tzinfo is None:
        raise ValueError("A timezone-aware observation timestamp is required")
    if not isfinite(current_price) or current_price <= 0:
        raise ValueError("Live price must be a positive finite value")
    lookback, interval_minutes = LOOKBACKS[period]
    now = now.astimezone(UTC)
    target = now - lookback
    step = timedelta(minutes=interval_minutes)
    prepared: list[tuple[datetime, dict[str, Any]]] = []
    for candle in candles:
        stamp = datetime.fromisoformat(candle["time"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Candle times must be UTC-aware")
        close_time = stamp.astimezone(UTC) + step
        # Defensive against a malformed/mixed upstream response that contains forming bars.
        if close_time > now:
            continue
        if not all(isfinite(float(candle[key])) and float(candle[key]) > 0
                   for key in ("close", "high", "low")):
            raise ValueError("Candle has invalid prices")
        if float(candle["low"]) > float(candle["high"]):
            raise ValueError("Candle high is lower than low")
        prepared.append((close_time, candle))
    prepared.sort(key=lambda x: x[0])
    references = [(stamp, row) for stamp, row in prepared if stamp <= target]
    if not references:
        raise ValueError("No completed historical close exists at/before window start")
    reference_time, reference = references[-1]
    # Prevent silently comparing against an ancient or large-gap candle.
    reference_age = (target - reference_time).total_seconds() / 60
    if reference_age > interval_minutes * 1.5:
        raise ValueError("Historical reference is too old for the selected window")
    base = float(reference["close"])
    in_window = [row for stamp, row in prepared if target < stamp <= now]
    # Include the live quote to avoid excluding its latest movement.
    high = max([current_price, *(float(row["high"]) for row in in_window)])
    low = min([current_price, *(float(row["low"]) for row in in_window)])
    return {
        "change_pct": round((current_price / base - 1) * 100, 3),
        "swing_pct": round((high - low) / base * 100, 3),
        "reference_close_usd": base,
        "reference_close_time_utc": reference_time.isoformat(),
        "observed_high_usd": high,
        "observed_low_usd": low,
        "reference_age_minutes": round(reference_age, 1),
        "ohlc_interval_minutes": interval_minutes,
        "methodology": (
            "Net change = (current spot price / reference completed close - 1) x 100. "
            "Range = (highest observed candle high - lowest observed candle low) "
            "/ reference close x 100, including the live quote. "
            "Reference is the latest completed candle close at/before the start of "
            "the selected trailing window; timing error is up to one candle interval. "
            "Not a realized-volatility measure."
        ),
    }
