"""Simple, explainable indicators computed only from completed market candles."""

import math
from typing import Any

import pandas as pd


def summarize_candles(candles: list[dict[str, Any]], interval_minutes: int) -> dict[str, Any]:
    if not candles:
        raise ValueError("At least one closed candle is required")
    if interval_minutes <= 0:
        raise ValueError("Candle interval must be positive")
    frame = pd.DataFrame(candles).sort_values("time").reset_index(drop=True)
    close = frame["close"].astype(float)
    if (close <= 0).any():
        raise ValueError("Close must be positive")

    frame["sma_20"] = close.rolling(20, min_periods=20).mean()
    frame["sma_50"] = close.rolling(50, min_periods=50).mean()
    change = close.diff()
    gain = change.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-change.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - 100 / (1 + rs)
    # Explicit edge cases: no losses -> 100, flat -> 50.
    rsi = rsi.mask((loss == 0) & (gain > 0), 100)
    rsi = rsi.mask((loss == 0) & (gain == 0), 50)

    log_returns = close.map(math.log).diff().dropna()
    lookback = int(7 * 1440 / interval_minutes)
    sample = log_returns.tail(lookback)
    realized_24h_vol = None
    if len(sample) >= 2:
        realized_24h_vol = float(sample.std(ddof=1) * math.sqrt(1440 / interval_minutes) * 100)

    change_7d = None
    if len(close) > lookback:
        change_7d = float((close.iloc[-1] / close.iloc[-lookback - 1] - 1) * 100)

    drawdown = close / close.cummax() - 1
    frame["sma_20"] = frame["sma_20"].where(frame["sma_20"].notna(), None)
    frame["sma_50"] = frame["sma_50"].where(frame["sma_50"].notna(), None)

    def optional(value: Any) -> float | None:
        return None if pd.isna(value) else round(float(value), 4)

    chart = [
        {
            "time": row["time"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume_base": float(row["volume_base"]),
            "sma_20": optional(row["sma_20"]),
            "sma_50": optional(row["sma_50"]),
        }
        for _, row in frame.iterrows()
    ]
    return {
        "interval_minutes": interval_minutes,
        "completed_candles": len(candles),
        "close_usd": float(close.iloc[-1]),
        "sma_20_usd": optional(frame["sma_20"].iloc[-1]),
        "sma_50_usd": optional(frame["sma_50"].iloc[-1]),
        "rsi_14": optional(rsi.iloc[-1]),
        "return_7d_pct": optional(change_7d),
        "realized_24h_vol_pct": optional(realized_24h_vol),
        "max_close_to_close_drawdown_pct": round(float(drawdown.min()) * 100, 4),
        "candles": chart,
        "methodology": (
            "Closed candles only. RSI(14) uses simple moving averages of gains/losses. "
            "Volatility is sample std. dev. of up to 7 days of log returns, scaled "
            "to 24 hours by sqrt(1440 / interval_minutes); not a VaR or forecast. "
            "Drawdown uses closing prices over the returned sample."
        ),
    }
