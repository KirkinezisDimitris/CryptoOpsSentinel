"""Deterministic historical risk tests, no exchange access required."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from cryptoops.api import app, get_market
from cryptoops.portfolio_analytics import InsufficientHistoryError, analyze_historical_risk
from cryptoops.risk import evaluate_portfolio


def sample_candles(days=110, offset=0):
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=offset)
    history = {}
    for symbol, initial in (("BTC", 100.0), ("ETH", 80.0), ("SOL", 40.0)):
        rows = []
        price = initial
        for day in range(days):
            # Bounded, non-constant, deterministic changes with intermittent losses.
            pct = ((day * (3 if symbol == "SOL" else 2)) % 13 - 6) / 1000
            price *= 1 + pct
            rows.append({"time": (start + timedelta(days=day)).isoformat(), "close": price})
        history[symbol] = rows
    return history


POSITIONS = [
    {"symbol": "BTC", "quantity": 1},
    {"symbol": "BTC", "quantity": 0.5},
    {"symbol": "ETH", "quantity": 2},
    {"symbol": "SOL", "quantity": 3},
]


def test_historical_analysis_measures_and_coverage():
    analysis = analyze_historical_risk(POSITIONS, sample_candles(), 1000, 90)
    assert analysis["sample_daily_returns"] == 90
    assert len(analysis["history"]) == 91
    assert analysis["daily_historical_var_pct"] >= 0
    assert (
        analysis["daily_historical_expected_shortfall_pct"]
        >= analysis["daily_historical_var_pct"]
    )
    assert analysis["daily_historical_var_usd"] == round(
        analysis["daily_historical_var_pct"] * 10, 2
    )
    assert analysis["historical_max_drawdown_pct"] <= 0
    assert len(analysis["asset_correlations"]) == 3
    assert "NOT actual trading performance" in analysis["methodology"]


def test_historical_risk_requires_synchronized_60_day_history():
    with pytest.raises(InsufficientHistoryError, match="at least 60"):
        analyze_historical_risk(POSITIONS, sample_candles(40), 1000, 90)


def test_historical_risk_rejects_missing_calendar_day():
    data = sample_candles(75)
    data["ETH"].pop(20)
    with pytest.raises(InsufficientHistoryError, match="missing UTC dates"):
        analyze_historical_risk(POSITIONS, data, 1000, 90)


def test_historical_risk_rejects_duplicate_candle():
    data = sample_candles()
    data["SOL"].append(data["SOL"][0])
    with pytest.raises(ValueError, match="repeated historical prices"):
        analyze_historical_risk(POSITIONS, data, 1000, 90)


def test_historical_risk_rejects_short_lookback():
    with pytest.raises(ValueError, match="between 60 and 365"):
        analyze_historical_risk(POSITIONS, sample_candles(), 1000, 30)


def test_constant_price_series_do_not_return_nan_correlations():
    data = sample_candles()
    for item in data["SOL"]:
        item["close"] = 40
    output = analyze_historical_risk(POSITIONS, data, 1000, 90)
    corr = next(row for row in output["asset_correlations"] if row["symbol"] == "SOL")
    assert corr["BTC"] is None
    assert corr["SOL"] is None


def test_allocation_and_stress_scenarios():
    portfolio = {
        "label": "Synthetic test",
        "positions": [
            {
                "symbol": "BTC", "venue": "Kraken", "venue_type": "CEX",
                "quantity": "1", "unit_cost_usd": "100",
            },
            {
                "symbol": "ETH", "venue": "Uniswap", "venue_type": "DEX",
                "quantity": "1", "unit_cost_usd": "100",
            },
        ],
        "risk_policy": {
            "max_single_asset_weight_pct": 90,
            "max_single_venue_weight_pct": 90,
            "unrealized_loss_alert_pct": -20,
        },
    }
    data = evaluate_portfolio(portfolio, [
        {"symbol": "BTC", "price_usd": 100}, {"symbol": "ETH", "price_usd": 100}
    ])
    assert data["diversification"]["herfindahl_index"] == 0.5
    assert data["diversification"]["effective_number_of_assets"] == 2
    assert len(data["by_venue_type"]) == 2
    shock = next(s for s in data["stress_scenarios"] if s["scenario"] == "Broad market -20%")
    assert shock["portfolio_value_after_usd"] == 160
    assert shock["change_from_current_usd"] == -40
    btc = next(s for s in data["stress_scenarios"] if s["scenario"].startswith("BTC -20%"))
    assert btc["change_from_current_usd"] == -20


class HistoryMarket:
    async def overview(self):
        return [
            {"symbol": "BTC", "price_usd": 70000},
            {"symbol": "ETH", "price_usd": 3200},
            {"symbol": "SOL", "price_usd": 160},
        ]

    async def candles(self, symbol, interval):
        assert interval == 1440
        return sample_candles(100)[symbol]


def test_historical_analytics_endpoint_with_mocked_exchange():
    app.dependency_overrides[get_market] = lambda: HistoryMarket()
    try:
        client = TestClient(app)
        response = client.get("/api/v1/portfolio/analytics?lookback_days=90")
        assert response.status_code == 200
        result = response.json()
        assert result["sample_daily_returns"] == 90
        assert "PAPER" in result["portfolio_mode"]
        assert len(result["history"]) == 91
        assert client.get("/api/v1/portfolio/analytics?lookback_days=10").status_code == 422
    finally:
        app.dependency_overrides.clear()
