"""Historical risk diagnostics for a static-quantity, hypothetical Spot portfolio.

Historical candles are actual Kraken closed daily candles, but the portfolio's
holdings are synthetic and are *retrospectively assumed constant*. This is NOT
realized strategy performance, investment advice, or a price forecast.
"""

from math import isfinite, sqrt
from typing import Any

import pandas as pd


class InsufficientHistoryError(ValueError):
    """Cannot estimate historical risk without adequate synchronized daily data."""


def analyze_historical_risk(
    positions: list[dict[str, Any]],
    candles_by_symbol: dict[str, list[dict[str, Any]]],
    market_value_usd: float,
    lookback_days: int = 180,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Compute *historical*, not forward-looking, empirical risk estimates.

    Daily return model uses a fixed number of units per asset (buy-and-hold).
    When estimating VaR/ES, historical percentage returns are scaled to the
    current spot-marked portfolio value. No historical trades or cash flows.
    """
    if not 60 <= lookback_days <= 365:
        raise ValueError("lookback_days must be between 60 and 365")
    if not 0.90 <= confidence <= 0.99:
        raise ValueError("confidence must be between 0.90 and 0.99")
    if not market_value_usd > 0:
        raise ValueError("Current portfolio value must be positive")

    quantities: dict[str, float] = {}
    for position in positions:
        symbol = position["symbol"]
        quantity = float(position["quantity"])
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        quantities[symbol] = quantities.get(symbol, 0.0) + quantity

    series = []
    for symbol in sorted(quantities):
        if symbol not in candles_by_symbol:
            raise InsufficientHistoryError(f"Missing historical candle data for {symbol}")
        df = pd.DataFrame(candles_by_symbol[symbol])
        if df.empty or not {"time", "close"}.issubset(df.columns):
            raise InsufficientHistoryError(f"Missing closed daily candles for {symbol}")
        times = pd.to_datetime(df["time"], utc=True, errors="coerce")
        closes = pd.to_numeric(df["close"], errors="coerce")
        data = pd.DataFrame({"time": times, symbol: closes}).dropna()
        if (data[symbol] <= 0).any() or data["time"].duplicated().any():
            raise ValueError(f"Invalid or repeated historical prices for {symbol}")
        data = data.set_index("time").sort_index()
        series.append(data)

    prices = pd.concat(series, axis=1, join="inner").dropna().tail(lookback_days + 1)
    if len(prices) < 61:
        raise InsufficientHistoryError(
            "Need at least 60 synchronized, completed daily return observations"
        )
    # Detect missing calendar days rather than accidentally measuring multi-day returns as daily.
    if not (prices.index.to_series().diff().dropna() == pd.Timedelta(days=1)).all():
        raise InsufficientHistoryError("Historical daily candles have missing UTC dates")

    synthetic_value = sum(prices[symbol] * quantity for symbol, quantity in quantities.items())
    daily_returns = synthetic_value.pct_change(fill_method=None).dropna()
    asset_returns = prices.pct_change(fill_method=None).dropna()
    if (daily_returns <= -1).any() or not daily_returns.notna().all():
        raise ValueError("Invalid historical return series")

    quantile = float(daily_returns.quantile(1 - confidence))
    expected_tail = float(daily_returns[daily_returns <= quantile].mean())
    daily_var_pct = max(0.0, -quantile * 100)
    daily_es_pct = max(0.0, -expected_tail * 100)
    daily_volatility = float(daily_returns.std(ddof=1))
    cummax = synthetic_value.cummax()
    drawdown = (synthetic_value / cummax - 1) * 100
    worst = float(daily_returns.min() * 100)
    best = float(daily_returns.max() * 100)
    portfolio_latest_close = float(synthetic_value.iloc[-1])

    correlation_df = asset_returns.corr()
    correlations = [
        {"symbol": symbol, **{
            other: (
                round(float(correlation_df.loc[symbol, other]), 4)
                if isfinite(float(correlation_df.loc[symbol, other])) else None
            )
            for other in quantities
        }}
        for symbol in quantities
    ]
    asset_metrics = []
    for symbol in quantities:
        asset = asset_returns[symbol]
        asset_metrics.append(
            {
                "symbol": symbol,
                "annualized_volatility_pct": round(float(asset.std(ddof=1) * sqrt(365) * 100), 2),
                "period_return_pct": round(
                    float((prices[symbol].iloc[-1] / prices[symbol].iloc[0] - 1) * 100), 2
                ),
            }
        )

    # Keep chart payload light; up to 366 points. Synthetic value is an *illustration*.
    history = [
        {
            "date_utc": ts.strftime("%Y-%m-%d"),
            "synthetic_buy_hold_value_usd": round(float(value), 2),
            "drawdown_pct": round(float(drawdown.loc[ts]), 3),
        }
        for ts, value in synthetic_value.items()
    ]
    return {
        "as_of_completed_candle_utc": prices.index[-1].isoformat(),
        "sample_daily_returns": len(daily_returns),
        "lookback_days_requested": lookback_days,
        "confidence_pct": round(confidence * 100, 1),
        "annualized_historical_volatility_pct": round(daily_volatility * sqrt(365) * 100, 2),
        "period_buy_hold_return_pct": round(
            (portfolio_latest_close / float(synthetic_value.iloc[0]) - 1) * 100, 2
        ),
        "historical_max_drawdown_pct": round(float(drawdown.min()), 2),
        "worst_observed_daily_return_pct": round(worst, 2),
        "best_observed_daily_return_pct": round(best, 2),
        "daily_historical_var_pct": round(daily_var_pct, 2),
        "daily_historical_var_usd": round(market_value_usd * daily_var_pct / 100, 2),
        "daily_historical_expected_shortfall_pct": round(daily_es_pct, 2),
        "daily_historical_expected_shortfall_usd": round(market_value_usd * daily_es_pct / 100, 2),
        "asset_correlations": correlations,
        "asset_historical_metrics": asset_metrics,
        "history": history,
        "methodology": (
            "Past completed daily Kraken Spot closes, aligned on identical UTC dates. "
            "A static number of units for each synthetic holding is assumed throughout the "
            "lookback period, with no trades, cash flows, fees, taxes, funding or rebalancing. "
            "Return volatility is sample standard deviation of daily portfolio returns "
            "annualized using sqrt(365). Empirical historical VaR is the negative lower "
            "return quantile; expected shortfall averages observations at/below that quantile. "
            "Positive lower quantiles are floored at zero loss. Both are backward-looking "
            "descriptive estimates, not guaranteed worst-case losses. USD amounts scale "
            "historical returns to the current live Kraken-marked value. "
            "The synthetic historical chart is NOT actual trading performance or P&L."
        ),
    }
