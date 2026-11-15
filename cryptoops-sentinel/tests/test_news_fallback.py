"""v0.3.1 recovery tests — providers are fully mocked, no network required."""
import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from cryptoops.news import NewsClient, NewsDataError, normalize_rss_articles

RSS_XML = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Bitcoin ETF inflows surge</title><link>https://example.com/bitcoin</link>
<pubDate>Sat, 14 Nov 2026 10:20:00 GMT</pubDate></item>
<item><title>Crypto markets brace for Fed news</title><link>https://example.com/crypto</link>
<pubDate>Sat, 14 Nov 2026 11:00:00 GMT</pubDate></item>
<item><title>Unsafe link</title><link>javascript:alert(1)</link></item>
</channel></rss>"""


def test_rss_normalizer_sanitizes_urls_and_tracks_time_provenance():
    items = normalize_rss_articles(RSS_XML, "CoinDesk", "BTC")
    assert len(items) == 2
    assert items[0]["observed_at_utc"] == "2026-11-14T10:20:00+00:00"
    assert "publication time" in items[0]["time_kind"]
    assert items[0]["source"] == "CoinDesk"
    assert items[0]["headline_relevance_score_pct"] > 20


def test_rss_invalid_xml_is_rejected():
    try:
        normalize_rss_articles(b"<rss><broken>", "CoinDesk", "BTC")
    except NewsDataError:
        return
    raise AssertionError("Malformed RSS must be rejected")


def test_gdelt_429_uses_backup_rss_then_caches_result():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        if "gdeltproject" in request.url.host:
            return httpx.Response(429, text="Too Many Requests")
        if "coindesk" in request.url.host:
            return httpx.Response(200, content=RSS_XML, headers={"content-type": "application/rss+xml"})
        return httpx.Response(503, text="Publisher offline")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            news = NewsClient(http)
            first = await news.search("BTC")
            again = await news.search("BTC")
            return first, again, news

    first, again, news = asyncio.run(run())
    assert first["coverage_available"]
    assert first["fallback_used"]
    assert "CoinDesk" in first["provider"]
    assert first == again
    assert len(first["articles"]) == 2
    assert len(urls) == 3
    assert news._gdelt_suspended_until is not None


def test_historical_gdelt_failure_does_not_substitute_current_rss():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(429, text="Too Many Requests")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await NewsClient(http).search("BTC", target_date=(datetime.now(UTC)-timedelta(days=3)).date())

    result = asyncio.run(run())
    assert not result["coverage_available"]
    assert not result["articles"]
    assert not result["fallback_used"]
    assert len(urls) == 1
    assert "not evidence" in result["note"]


def test_when_gdelt_is_healthy_rss_is_not_requested():
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200, json={"articles": []}, headers={"content-type": "application/json"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await NewsClient(http).search("BTC")

    result = asyncio.run(run())
    assert result["coverage_available"]
    assert not result["fallback_used"]
    assert calls == ["api.gdeltproject.org"]
