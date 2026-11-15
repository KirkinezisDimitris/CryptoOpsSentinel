"""Daily analyst-style market/risk reporting from an explicit live snapshot."""

from datetime import UTC, datetime
from typing import Any


def render_daily_report(
    tickers: list[dict[str, Any]], portfolio: dict[str, Any]
) -> dict[str, str]:
    created = datetime.now(UTC)
    lines = [
        "# CryptoOps Sentinel — Daily Market & Risk Brief",
        "",
        f"**Generated (UTC):** {created.strftime('%Y-%m-%d %H:%M:%S')}",
        "**Market feed:** Kraken Spot REST API (public, indicative spot prices)",
        "**Portfolio:** Synthetic paper holdings. No exchange or wallet integration.",
        "",
        "## Market overview",
        "",
        "| Pair | Last (USD) | Change since UTC open | 24h volume (base) | Spread |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for ticker in tickers:
        lines.append(
            f"| {ticker['market']} | ${ticker['price_usd']:,.2f} | "
            f"{ticker['change_since_utc_open_pct']:+.2f}% | "
            f"{ticker['volume_base_24h']:,.2f} | {ticker['spread_pct']:.3f}% |"
        )
    lines += [
        "",
        "## Paper portfolio summary",
        "",
        f"- Mark-to-market value: **${portfolio['market_value_usd']:,.2f}**",
        f"- Hypothetical cost basis: **${portfolio['cost_basis_usd']:,.2f}**",
        f"- Unrealized P&L: **{portfolio['unrealized_pnl_usd']:+,.2f} USD** "
        f"({portfolio['unrealized_pnl_pct']:+.2f}%)",
        f"- Illustrative risk status: **{portfolio['risk_status']}**",
        "",
        "## Risk observations",
        "",
    ]
    if diversity := portfolio.get("diversification"):
        lines.extend([
            f"- Largest asset exposure: **{diversity['largest_asset']}** "
            f"({diversity['largest_asset_weight_pct']:.2f}%)",
            f"- Effective number of assets (HHI-based): "
            f"**{diversity['effective_number_of_assets']:.2f}**",
        ])
    if portfolio["alerts"]:
        lines.extend(f"- {item['code']}: {item['message']}" for item in portfolio["alerts"])
    else:
        lines.append("- No demo policy breaches detected at this snapshot.")
    lines += [
        "",
        "## Deterministic spot-price stress scenarios",
        "",
        "| Hypothetical price shock | Portfolio value (USD) | Change vs now (USD) |",
        "| --- | ---: | ---: |",
    ]
    for scenario in portfolio.get("stress_scenarios", []):
        lines.append(
            f"| {scenario['scenario']} | ${scenario['portfolio_value_after_usd']:,.2f} | "
            f"{scenario['change_from_current_usd']:+,.2f} |"
        )
    lines += [
        "",
        "## Data and methodological limitations",
        "",
        "- Price is the latest Kraken spot trade, not an executable execution quote.",
        "- Change is against the current UTC opening price, not a rolling 24h return.",
        "- 24h base volume is venue-specific, not consolidated global volume.",
        "- Unrealized P&L excludes realized trades, fees, funding, taxes and slippage.",
        "- Spot stress scenarios are deterministic mark changes, not probability forecasts.",
        "- All venue labels use Kraken price marks; venue balances are not authenticated.",
        "- Historical VaR is a separate API analysis and is not included in this live brief.",
        "- These holdings are invented for demonstration; they are not actual financial records.",
        "- Signals and alerts are monitoring aids, not trading recommendations.",
        "",
        "*For software demonstration and education. Not investment advice.*",
        "",
    ]
    return {
        "filename": f"cryptoops-brief-{created.strftime('%Y-%m-%d')}.md",
        "generated_at_utc": created.isoformat(),
        "content_markdown": "\n".join(lines),
    }
