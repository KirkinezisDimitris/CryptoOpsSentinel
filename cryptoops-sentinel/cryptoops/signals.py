"""Educational, deterministic technical-bias rubric; never a forecast or advice."""
from __future__ import annotations

from typing import Any


def technical_bias(summary: dict[str, Any]) -> dict[str, Any]:
    """Return a 0-100 directional bias with transparent additive contributions.

    50 is neutral. This is NOT probability of profit or a recommendation.
    Uses only *completed* candles; deliberately ignores future outcomes and news.
    """
    rsi = summary.get("rsi_14")
    sma20 = summary.get("sma_20_usd")
    sma50 = summary.get("sma_50_usd")
    close = summary.get("close_usd")
    if any(value is None for value in (rsi, sma20, sma50, close)):
        return {"score_pct": None, "label": "INSUFFICIENT_DATA", "drivers": [],
                "meaning": "At least 50 completed candles required. No signal calculated."}
    if not 0 <= rsi <= 100 or min(sma20, sma50, close) <= 0:
        raise ValueError("Invalid technical indicators")
    drivers: list[dict[str, Any]] = []
    score = 50

    def add(name: str, points: int, explanation: str) -> None:
        nonlocal score
        score += points
        drivers.append({"metric": name, "points": points, "interpretation": explanation})

    add("Close vs SMA20", 15 if close > sma20 else (-15 if close < sma20 else 0),
        "Above shorter-term average supports momentum; below it weakens momentum.")
    add("SMA20 vs SMA50", 25 if sma20 > sma50 else (-25 if sma20 < sma50 else 0),
        "20-period average relative to 50-period average is a trend proxy, not a crossover date.")
    if rsi < 30:
        rsi_score = 10
        explanation = "Oversold readings can suggest mean reversion, but downtrends can persist."
    elif rsi > 70:
        rsi_score = -10
        explanation = "Overbought readings can suggest pullback risk, but uptrends can persist."
    elif 50 < rsi <= 70:
        rsi_score = 10
        explanation = "Moderate positive momentum."
    elif 30 <= rsi < 50:
        rsi_score = -10
        explanation = "Moderate negative momentum."
    else:
        rsi_score = 0
        explanation = "Neutral RSI."
    add("RSI14", rsi_score, explanation)
    score = max(0, min(100, score))
    label = "BUY_BIAS" if score >= 65 else ("SELL_BIAS" if score <= 35 else "HOLD_NEUTRAL")
    return {
        "score_pct": score, "label": label,
        "drivers": drivers,
        "meaning": (
            "Rule-based directional technical BIAS on completed candles, centered at 50. "
            "Not a calibrated probability, expected return, recommendation, or order trigger. "
            "Does not factor fees, derivatives, fundamentals, news, liquidity or portfolio suitability."
        ),
        "thresholds": {"sell_bias_at_or_below": 35, "hold": "36-64", "buy_bias_at_or_above": 65},
    }
