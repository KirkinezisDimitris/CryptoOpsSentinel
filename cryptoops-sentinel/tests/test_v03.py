"""All v0.3 tests use deterministic fixtures and require no exchange connectivity."""
import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from cryptoops.api import app, get_market, parse_symbols
from cryptoops.events import event_window
from cryptoops.glossary import GLOSSARY, METRIC_GUIDE
from cryptoops.live import LiveFeed, parse_ticker_message
from cryptoops.news import NewsClient, NewsDataError, normalize_articles, relevance
from cryptoops.signals import technical_bias


def good_summary(**overrides):
    return {"rsi_14": 55, "sma_20_usd": 110, "sma_50_usd": 100,
            "close_usd": 115, **overrides}


def test_bias_bullish_components():
    score = technical_bias(good_summary())
    assert score["score_pct"] == 100  # 50 + 15 + 25 + 10
    assert score["label"] == "BUY_BIAS"
    assert sum(x["points"] for x in score["drivers"]) + 50 == score["score_pct"]


def test_bias_bearish_components():
    score = technical_bias(good_summary(close_usd=80, sma_20_usd=90,
                                        sma_50_usd=100, rsi_14=42))
    assert score["score_pct"] == 0
    assert score["label"] == "SELL_BIAS"


def test_bias_neutral_and_data_shortage():
    assert technical_bias(good_summary(rsi_14=50, close_usd=110,
                                       sma_20_usd=110, sma_50_usd=110))["label"] == "HOLD_NEUTRAL"
    assert technical_bias(good_summary(sma_50_usd=None))["score_pct"] is None


def test_bias_invalid_input():
    try:
        technical_bias(good_summary(rsi_14=300))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid RSI to be rejected")


def test_glossary_has_unique_terms_and_explainers():
    assert len(GLOSSARY) >= 60
    assert len(set(e["term"] for e in GLOSSARY)) == len(GLOSSARY)
    assert all(e["affected_by"] and e["how_to_interpret"] for e in GLOSSARY)
    assert "Directional bias %" in METRIC_GUIDE


def test_glossary_filter_api():
    response = TestClient(app).get("/api/v1/glossary", params={"q": "RSI"})
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert all("rsi" in " ".join(str(x) for x in entry.values()).lower()
               for entry in response.json()["terms"])


def test_assets_api():
    res = TestClient(app).get("/api/v1/assets")
    assert res.status_code == 200
    assert "DOGE" in res.json()["symbols"]
    assert res.json()["default_watchlist"] == ["BTC", "ETH", "SOL"]


def test_watchlist_input_is_strict():
    assert parse_symbols("BTC,ETH,BTC") == ["BTC", "ETH"]
    assert TestClient(app).get("/api/v1/live?symbols=FAKE").status_code == 422
    assert TestClient(app).get("/api/v1/markets/FAKE/history?days=30").status_code == 422


def test_ws_normalization():
    msg = {"channel": "ticker", "type": "update", "data": [
        {"symbol": "BTC/USD", "last": 70000, "bid": 69999, "ask": 70001,
         "change_pct": 1.9, "volume": 123.0, "timestamp": "2026-11-15T00:00:00.123Z"},
        {"symbol": "ABC/USD", "last": 1, "bid": 1, "ask": 1,
         "timestamp": "2026-11-15T00:00:00Z"},
    ]}
    items = parse_ticker_message(msg)
    assert len(items) == 1 and items[0]["symbol"] == "BTC"
    assert items[0]["change_24h_pct"] == 1.9
    assert items[0]["spread_pct"] > 0


def test_ws_rejects_crossed_or_malformed():
    msg = {"channel": "ticker", "data": [
        {"symbol": "ETH/USD", "last": 100, "bid": 102, "ask": 101,
         "timestamp": "2026-11-15T00:00:00Z"},
        {"symbol": "ETH/USD", "bid": 102},
    ]}
    assert parse_ticker_message(msg) == []
    assert parse_ticker_message({"event": "heartbeat"}) == []


def test_ws_staleness_protection():
    feed = LiveFeed()
    quote = parse_ticker_message({"channel": "ticker", "data": [{
        "symbol": "BTC/USD", "last": 1, "bid": 1, "ask": 1,
        "timestamp": "2026-11-15T00:00:00Z"}]})[0]
    feed.latest_by_symbol["BTC"] = quote
    assert len(feed.snapshot(["BTC"])["quotes"]) == 1
    feed.latest_by_symbol["BTC"]["fetched_at_utc"] = (
        datetime.now(UTC) - timedelta(minutes=3)).isoformat()
    assert feed.snapshot(["BTC"])["missing_symbols"] == ["BTC"]


def test_news_headline_relevance():
    relevant = relevance("Bitcoin ETF approved by regulator", "BTC")
    unrelated = relevance("Weather is sunny in London", "BTC")
    assert relevant["headline_relevance_score_pct"] > unrelated["headline_relevance_score_pct"]
    assert "Regulatory" in relevant["categories"]


def test_news_normalizer_dedupes_and_ignores_unsafe_urls():
    records = normalize_articles({"articles": [
        {"title": "Bitcoin ETF", "url": "https://example.org/a", "seendate": "20261114000000"},
        {"title": "Bitcoin ETF again", "url": "https://example.org/a"},
        {"title": "Bad link", "url": "javascript:alert(1)"},
    ]}, "BTC")
    assert len(records) == 1
    assert records[0]["observed_at_utc"].startswith("2026-11-14")


def test_news_outside_coverage_is_not_reported_as_no_news():
    old = date.today() - timedelta(days=200)
    response = asyncio.run(NewsClient().search("BTC", target_date=old))
    assert not response["coverage_available"]
    assert "90 days" in response["note"]


def test_news_client_returns_real_fixture_results_and_caches():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "application/json"}, json={
            "articles": [{"title": "Ethereum ETF update", "url": "https://example.org/eth",
                          "seendate": "20261114000000"}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = NewsClient(http)
            one = await client.search("ETH")
            two = await client.search("ETH")
            return one, two
    one, two = asyncio.run(run())
    assert len(calls) == 1
    assert one == two and len(one["articles"]) == 1
    assert one["articles"][0]["headline_relevance_score_pct"] > 20


def test_news_provider_non_json_and_failed_feeds_report_unavailable():
    def handler(_request):
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="rate limited")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await NewsClient(http).search("BTC")

    result = asyncio.run(run())
    assert not result["coverage_available"]
    assert result["fallback_used"]
    assert not result["articles"]
    assert "NOT proof" in result["note"]


def test_event_window_uses_adjacent_daily_closes():
    rows = [
        {"time": "2026-11-10T00:00:00+00:00", "close": 100},
        {"time": "2026-11-11T00:00:00+00:00", "close": 110},
        {"time": "2026-11-12T00:00:00+00:00", "close": 99},
    ]
    value = event_window(rows, date(2026, 11, 11))
    assert value["previous_to_selected_day_pct"] == 10
    assert value["selected_to_next_day_pct"] == -10
    assert len(value["surrounding_completed_daily_closes"]) == 3
    assert "CANNOT" in value["methodology"]


def test_event_window_handles_missing_dates_without_faking_change():
    value = event_window([], date(2026, 11, 11))
    assert value["previous_to_selected_day_pct"] is None
    assert value["selected_completed_close_usd"] is None


def test_invalid_historical_date_422_without_api_call():
    response = TestClient(app).get("/api/v1/events/BTC", params={
        "selected_date": "2011-01-01"})
    assert response.status_code == 422


def test_unsupported_news_coin_is_rejected():
    response = TestClient(app).get("/api/v1/news?symbol=BAD")
    assert response.status_code == 422

class FakeHistoricalMarket:
    async def candles(self, symbol, interval):
        assert symbol == "BTC"
        if interval == 1440:
            days = 10
            step = timedelta(days=1)
        else:
            days = 100
            step = timedelta(minutes=interval)
        end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return [{
            "time": (end - (days - index) * step).isoformat(),
            "open": 100 + index, "high": 102 + index, "low": 99 + index,
            "close": 101 + index, "volume_base": 10,
        } for index in range(days)]


def test_historical_market_api_has_explainable_bias_and_completed_candles():
    app.dependency_overrides[get_market] = lambda: FakeHistoricalMarket()
    try:
        response = TestClient(app).get("/api/v1/markets/BTC/history?days=30")
        assert response.status_code == 200
        payload = response.json()
        assert payload["interval_minutes"] == 240
        assert len(payload["candles"]) >= 50
        assert 0 <= payload["technical_bias"]["score_pct"] <= 100
        assert payload["technical_bias"]["drivers"]
    finally:
        app.dependency_overrides.clear()


def test_event_context_api_uses_mock_daily_candles():
    app.dependency_overrides[get_market] = lambda: FakeHistoricalMarket()
    try:
        selected = (datetime.now(UTC).date() - timedelta(days=4)).isoformat()
        response = TestClient(app).get("/api/v1/events/BTC", params={"selected_date": selected})
        assert response.status_code == 200
        assert response.json()["selected_date_utc"] == selected
        assert response.json()["surrounding_completed_daily_closes"]
    finally:
        app.dependency_overrides.clear()
