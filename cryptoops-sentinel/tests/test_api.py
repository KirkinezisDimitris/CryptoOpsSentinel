from fastapi.testclient import TestClient

from cryptoops.api import app, get_market


class FakeMarket:
    async def overview(self):
        return [{"symbol": "BTC", "price_usd": 100, "source": "test"}]


def test_health():
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"


def test_public_market_route_dependency_override():
    app.dependency_overrides[get_market] = lambda: FakeMarket()
    try:
        client = TestClient(app)
        response = client.get("/api/v1/markets")
        assert response.status_code == 200
        assert response.json()["markets"][0]["price_usd"] == 100
    finally:
        app.dependency_overrides.clear()


def test_unknown_symbol_is_rejected_before_exchange_request():
    client = TestClient(app)
    assert client.get("/api/v1/markets/FAKE/candles").status_code == 422


class FakeThreeMarket:
    async def overview(self):
        return [
            {
                "symbol": symbol,
                "market": f"{symbol}/USD",
                "price_usd": price,
                "source": "Mock public feed",
                "change_since_utc_open_pct": 1.0,
                "volume_base_24h": 12.0,
                "spread_pct": 0.1,
            }
            for symbol, price in [("BTC", 75000), ("ETH", 3000), ("SOL", 150)]
        ]


def test_portfolio_and_report_end_to_end_with_mocked_feed():
    app.dependency_overrides[get_market] = lambda: FakeThreeMarket()
    try:
        client = TestClient(app)
        response = client.get("/api/v1/portfolio")
        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) == 3
        assert data["market_value_usd"] > 0
        assert "PAPER" in data["mode"]

        report = client.get("/api/v1/report/daily")
        assert report.status_code == 200
        assert "Hypothetical cost basis" in report.json()["content_markdown"]
    finally:
        app.dependency_overrides.clear()
