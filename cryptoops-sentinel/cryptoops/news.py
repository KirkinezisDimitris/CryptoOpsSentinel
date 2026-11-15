"""GDELT DOC 2.0 headline retrieval; no fabricated articles, no causal claims.

The public ArtList API only exposes approximately the latest three months.
"""
from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx

from cryptoops.config import SUPPORTED_PAIRS

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
# Publisher-controlled public RSS feeds, used only for RECENT news when GDELT fails.
# These RSS feeds cannot provide complete historical searches.
RSS_SOURCES = (
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
)
RSS_MAX_BYTES = 1_000_000

ASSET_TERMS = {
    "BTC": '"Bitcoin"', "ETH": '"Ethereum"', "SOL": '"Solana"',
    "XRP": '"XRP"', "ADA": '"Cardano"', "DOGE": '"Dogecoin"',
    "LTC": '"Litecoin"', "LINK": '"Chainlink"',
    "DOT": '"Polkadot"', "AVAX": '"Avalanche"',
}
IMPACT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Regulatory": ("sec", "regulat", "lawsuit", "ban ", "legislation", "government", "court", "approval"),
    "Macro": ("federal reserve", "interest rate", "inflation", "cpi", "fomc", "jobs report", "recession"),
    "Institutional": ("etf", "institutional", "blackrock", "fund inflow", "fund outflow"),
    "Security": ("hack", "exploit", "breach", "security", "stolen", "attack"),
    "Market structure": ("liquidat", "exchange", "whale", "funding", "leverag", "bankrupt", "custody"),
    "Protocol": ("upgrade", "hard fork", "network outage", "mainnet", "token unlock"),
}


class NewsDataError(Exception):
    pass


def relevance(title: str, symbol: str) -> dict[str, Any]:
    """Transparent keyword rank (not sentiment or predicted price impact)."""
    normalized = title.casefold()
    categories = [
        category for category, words in IMPACT_KEYWORDS.items()
        if any(word in normalized for word in words)
    ]
    asset_name = ASSET_TERMS.get(symbol, "").strip('"').casefold()
    asset_match = asset_name in normalized or symbol.casefold() in normalized.split()
    score = min(100, 20 + 20 * bool(asset_match) + 25 * len(categories))
    return {
        "headline_relevance_score_pct": int(score),
        "categories": categories or ["General coverage"],
        "reason": (
            "Headline keyword match for asset and event categories. "
            "A relevance heuristic, NOT evidence of price impact or sentiment."
        ),
    }


def normalize_articles(payload: dict[str, Any], symbol: str, limit: int = 15) -> list[dict[str, Any]]:
    articles = payload.get("articles", [])
    if not isinstance(articles, list):
        raise NewsDataError("Invalid GDELT article list")
    result: list[dict[str, Any]] = []
    seen = set()
    for item in articles:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        domain = urlparse(url).hostname
        if not title or not domain or urlparse(url).scheme not in ("https", "http"):
            continue
        if url in seen:
            continue
        seen.add(url)
        stamp = str(item.get("seendate", ""))
        observed = None
        try:
            observed = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat()
        except ValueError:
            pass
        result.append({
            "title": title[:300], "url": url, "domain": domain,
            "observed_at_utc": observed, "time_kind": "GDELT first-seen (not publication time)",
            **relevance(title, symbol),
        })
    result.sort(key=lambda x: (x["headline_relevance_score_pct"], x["observed_at_utc"] or ""),
                reverse=True)
    return result[:limit]


def normalize_rss_articles(xml_data: bytes, source: str, symbol: str) -> list[dict[str, Any]]:
    """Parse publisher RSS without inventing headlines, timestamps or asset relevance."""
    if len(xml_data) > RSS_MAX_BYTES:
        raise NewsDataError(f"{source} RSS feed too large")
    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as exc:
        raise NewsDataError(f"{source} RSS feed is not valid XML") from exc
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        parsed_url = urlparse(url)
        if not title or parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            continue
        if url in seen:
            continue
        seen.add(url)
        published = None
        date_value = (item.findtext("pubDate") or "").strip()
        if date_value:
            try:
                stamp = parsedate_to_datetime(date_value)
                if stamp.tzinfo is not None:
                    published = stamp.astimezone(UTC).isoformat()
            except (TypeError, ValueError, IndexError):
                pass
        result.append({
            "title": title[:300], "url": url, "domain": parsed_url.hostname,
            "observed_at_utc": published,
            "time_kind": "RSS publication time reported by publisher (not independently verified)",
            "source": source, **relevance(title, symbol),
        })
    return result


class NewsClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client
        self._cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._last_request_at: datetime | None = None
        self._gdelt_suspended_until: datetime | None = None

    async def search(self, symbol: str, *, target_date: date | None = None,
                     limit: int = 15) -> dict[str, Any]:
        symbol = symbol.upper()
        if symbol not in SUPPORTED_PAIRS or not 1 <= limit <= 30:
            raise ValueError("Unsupported news request")
        now = datetime.now(UTC)
        if target_date is not None:
            requested = datetime.combine(target_date, time.min, UTC)
            if requested > now:
                return self._unavailable(symbol, "Future date; no news can be retrieved", target_date)
            if (now - requested).days > 89:
                return self._unavailable(
                    symbol, "Article search is limited to the recent ~90 days by GDELT DOC 2.0; "
                            "older days are NOT evidence that there was no news", target_date
                )
            start = requested - timedelta(days=1)
            end = min(now, requested + timedelta(days=2))
            if start < now - timedelta(days=90):
                start = now - timedelta(days=89)
            date_window = {
                "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                "enddatetime": end.strftime("%Y%m%d%H%M%S"),
            }
        else:
            date_window = {"timespan": "2d"}
        # Match asset-specific coverage, macro + broad crypto relevant events.
        query = f'({ASSET_TERMS[symbol]} OR "cryptocurrency")'
        params = {"query": query, "mode": "ArtList", "format": "json", "maxrecords": 60,
                  "sort": "DateDesc", **date_window}
        key = f"{symbol}|{target_date}|{limit}"
        cached = self._cache.get(key)
        if cached is not None and (now - cached[0]).total_seconds() < (600 if target_date is None else 3600):
            return cached[1]
        async with self._lock:
            now = datetime.now(UTC)
            cached = self._cache.get(key)
            if cached is not None and (now - cached[0]).total_seconds() < (600 if target_date is None else 3600):
                return cached[1]
            failure_reason = None
            if self._gdelt_suspended_until is not None and now < self._gdelt_suspended_until:
                failure_reason = "GDELT temporarily paused after a provider failure"
            else:
                # GDELT requires traffic pacing. Don't retry a failed provider on every rerun.
                if self._last_request_at is not None:
                    seconds = (now - self._last_request_at).total_seconds()
                    if seconds < 5.5:
                        await asyncio.sleep(5.5 - seconds)
                self._last_request_at = datetime.now(UTC)
                try:
                    if self.client is not None:
                        response = await self.client.get(BASE_URL, params=params, timeout=12)
                    else:
                        async with httpx.AsyncClient(timeout=12) as client:
                            response = await client.get(BASE_URL, params=params)
                    response.raise_for_status()
                    if "json" not in response.headers.get("content-type", "").lower():
                        raise NewsDataError("GDELT returned non-JSON data")
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise NewsDataError("GDELT returned an invalid article list")
                    result = {
                        "symbol": symbol,
                        "target_date_utc": target_date.isoformat() if target_date else None,
                        "coverage_available": True,
                        "provider": "GDELT DOC 2.0",
                        "fallback_used": False,
                        "articles": normalize_articles(payload, symbol, limit),
                        "fetched_at_utc": datetime.now(UTC).isoformat(),
                        "note": (
                            "Headlines are ranked using transparent keywords, not inferred market impact. "
                            "GDELT first-seen time may not equal the original publication time. "
                            "Search results may be incomplete."
                        ),
                    }
                    self._gdelt_suspended_until = None
                    self._cache[key] = (datetime.now(UTC), result)
                    return result
                except (NewsDataError, httpx.HTTPError, ValueError) as exc:
                    failure_reason = f"GDELT request failed ({type(exc).__name__})"
                    self._gdelt_suspended_until = datetime.now(UTC) + timedelta(minutes=10)

            if target_date is not None:
                # Never substitute today's RSS articles for a historical date.
                result = self._unavailable(
                    symbol,
                    f"Historical article coverage unavailable: {failure_reason}. "
                    "Try the dated external news search link. This is not evidence that no news occurred.",
                    target_date,
                )
                result["fallback_used"] = False
            else:
                result = await self._recent_rss_fallback(symbol, limit, failure_reason or "Provider failure")
            self._cache[key] = (datetime.now(UTC), result)
            return result

    async def _recent_rss_fallback(self, symbol: str, limit: int, reason: str) -> dict[str, Any]:
        articles: list[dict[str, Any]] = []
        used_sources: list[str] = []
        # Single client for both feeds; mock client can be injected for deterministic tests.
        async def fetch_feed(client: httpx.AsyncClient, name: str, url: str) -> None:
            try:
                response = await client.get(url, timeout=8, follow_redirects=True)
                response.raise_for_status()
                rows = normalize_rss_articles(response.content, name, symbol)
            except (httpx.HTTPError, NewsDataError):
                return  # One failed publisher must not hide the other provider's headlines.
            if rows:
                used_sources.append(name)
                articles.extend(rows)

        if self.client is not None:
            for name, url in RSS_SOURCES:
                await fetch_feed(self.client, name, url)
        else:
            async with httpx.AsyncClient(timeout=8) as client:
                for name, url in RSS_SOURCES:
                    await fetch_feed(client, name, url)

        if not articles:
            return {
                "symbol": symbol, "target_date_utc": None, "coverage_available": False,
                "provider": "GDELT + publisher RSS", "fallback_used": True,
                "articles": [], "fetched_at_utc": datetime.now(UTC).isoformat(),
                "note": f"No news provider could be reached ({reason}). This is NOT proof that no news happened.",
            }
        dedup: dict[str, dict[str, Any]] = {x["url"]: x for x in articles}
        ranked = sorted(
            dedup.values(),
            key=lambda x: (x["headline_relevance_score_pct"], x["observed_at_utc"] or ""),
            reverse=True,
        )[:limit]
        return {
            "symbol": symbol, "target_date_utc": None, "coverage_available": True,
            "provider": "Publisher RSS: " + ", ".join(used_sources),
            "fallback_used": True,
            "articles": ranked, "fetched_at_utc": datetime.now(UTC).isoformat(),
            "note": (
                f"GDELT unavailable ({reason}); showing recent publisher RSS headlines instead. "
                "Feed publication timestamps are publisher-provided. These may include broad "
                "crypto news, not only the selected asset. RSS is NOT a historical archive "
                "and coverage is incomplete. Relevance score is not market impact."
            ),
        }

    @staticmethod
    def _unavailable(symbol: str, note: str, target_date: date | None = None) -> dict[str, Any]:
        return {"symbol": symbol, "coverage_available": False, "articles": [],
                "target_date_utc": target_date.isoformat() if target_date else None,
                "provider": "GDELT DOC 2.0", "note": note}
