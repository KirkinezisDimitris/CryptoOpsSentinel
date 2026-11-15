import pytest

from cryptoops.risk import evaluate_portfolio


@pytest.fixture
def paper():
    return {
        "label": "Synthetic fixture",
        "positions": [
            {
                "symbol": "BTC", "venue": "Kraken", "venue_type": "CEX",
                "quantity": "1", "unit_cost_usd": "100",
            },
            {
                "symbol": "ETH", "venue": "Coinbase", "venue_type": "CEX",
                "quantity": "2", "unit_cost_usd": "50",
            },
        ],
        "risk_policy": {
            "max_single_asset_weight_pct": 55,
            "max_single_venue_weight_pct": 75,
            "unrealized_loss_alert_pct": -20,
        },
    }


def test_portfolio_cost_and_unrealized_pnl(paper):
    result = evaluate_portfolio(
        paper, [{"symbol": "BTC", "price_usd": 120}, {"symbol": "ETH", "price_usd": 40}]
    )
    assert result["market_value_usd"] == 200
    assert result["cost_basis_usd"] == 200
    assert result["unrealized_pnl_usd"] == 0
    assert result["positions"][0]["unrealized_pnl_usd"] == 20
    assert result["positions"][1]["unrealized_pnl_usd"] == -20
    assert any(a["code"] == "ASSET_CONCENTRATION" for a in result["alerts"])
    assert result["risk_status"] == "ALERT"


def test_no_alerts_with_equal_exposures(paper):
    result = evaluate_portfolio(
        paper, [{"symbol": "BTC", "price_usd": 100}, {"symbol": "ETH", "price_usd": 50}]
    )
    assert result["risk_status"] == "WITHIN_DEMO_LIMITS"
    assert result["by_asset"][0]["weight_pct"] == 50
    assert len(result["alerts"]) == 0


def test_unrealized_loss_alert(paper):
    result = evaluate_portfolio(
        paper, [{"symbol": "BTC", "price_usd": 100}, {"symbol": "ETH", "price_usd": 20}]
    )
    assert any(a["code"] == "UNREALIZED_LOSS" for a in result["alerts"])


def test_missing_price_fails_closed(paper):
    with pytest.raises(ValueError, match="not supported"):
        evaluate_portfolio(paper, [{"symbol": "BTC", "price_usd": 100}])


def test_invalid_quantity_rejected(paper):
    paper["positions"][0]["quantity"] = "-1"
    with pytest.raises(ValueError, match="must be positive"):
        evaluate_portfolio(
            paper, [{"symbol": "BTC", "price_usd": 100}, {"symbol": "ETH", "price_usd": 50}]
        )
