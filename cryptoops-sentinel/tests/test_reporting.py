from cryptoops.reporting import render_daily_report


def test_report_discloses_synthetic_holdings_and_utc_open():
    report = render_daily_report(
        [
            {
                "market": "BTC/USD", "price_usd": 100,
                "change_since_utc_open_pct": 2.0,
                "volume_base_24h": 20,
                "spread_pct": 0.1,
            }
        ],
        {
            "market_value_usd": 100,
            "cost_basis_usd": 80,
            "unrealized_pnl_usd": 20,
            "unrealized_pnl_pct": 25,
            "risk_status": "WITHIN_DEMO_LIMITS",
            "alerts": [],
        },
    )
    assert report["filename"].startswith("cryptoops-brief-")
    assert "Synthetic paper holdings" in report["content_markdown"]
    assert "UTC opening" in report["content_markdown"]
    assert "No demo policy breaches" in report["content_markdown"]
