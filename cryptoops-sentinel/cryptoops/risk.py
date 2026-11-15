"""Decimal-based valuation of a deliberately hypothetical paper portfolio."""

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from cryptoops.config import PORTFOLIO_FILE, SUPPORTED_PAIRS


def load_demo_portfolio(path: Path = PORTFOLIO_FILE) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("positions"):
        raise ValueError("Demo portfolio must include positions")
    return data


def _d(value: Any) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Amount must be finite")
    return number


def evaluate_portfolio(portfolio: dict[str, Any], tickers: list[dict[str, Any]]) -> dict[str, Any]:
    prices = {t["symbol"]: _d(t["price_usd"]) for t in tickers}
    policy = portfolio["risk_policy"]
    position_limit = _d(policy["max_single_asset_weight_pct"])
    venue_limit = _d(policy["max_single_venue_weight_pct"])
    loss_limit = _d(policy["unrealized_loss_alert_pct"])

    positions: list[dict[str, Any]] = []
    asset_values: dict[str, Decimal] = defaultdict(Decimal)
    venue_values: dict[str, Decimal] = defaultdict(Decimal)
    venue_type_values: dict[str, Decimal] = defaultdict(Decimal)
    total_market_value = Decimal(0)
    total_cost = Decimal(0)

    for holding in portfolio["positions"]:
        symbol = holding["symbol"]
        if symbol not in SUPPORTED_PAIRS or symbol not in prices:
            raise ValueError(f"Position is not supported by live price feed: {symbol}")
        quantity = _d(holding["quantity"])
        unit_cost = _d(holding["unit_cost_usd"])
        if quantity <= 0 or unit_cost <= 0 or prices[symbol] <= 0:
            raise ValueError("Quantity, historical unit cost and live price must be positive")
        value = quantity * prices[symbol]
        cost = quantity * unit_cost
        unrealized = value - cost
        unrealized_pct = (unrealized / cost) * 100
        total_market_value += value
        total_cost += cost
        asset_values[symbol] += value
        venue_values[holding["venue"]] += value
        venue_type_values[holding["venue_type"]] += value
        positions.append(
            {
                "symbol": symbol,
                "venue": holding["venue"],
                "venue_type": holding["venue_type"],
                "quantity": float(quantity),
                "unit_cost_usd": float(unit_cost),
                "live_price_usd": float(prices[symbol]),
                "market_value_usd": round(float(value), 2),
                "unrealized_pnl_usd": round(float(unrealized), 2),
                "unrealized_pnl_pct": round(float(unrealized_pct), 2),
            }
        )

    if total_market_value <= 0:
        raise ValueError("Portfolio market value must be positive")

    for position in positions:
        position["weight_pct"] = round(
            float(_d(position["market_value_usd"]) / total_market_value * 100), 2
        )

    alerts: list[dict[str, Any]] = []
    for symbol, value in asset_values.items():
        weight = value / total_market_value * 100
        if weight > position_limit:
            alerts.append(
                {
                    "code": "ASSET_CONCENTRATION",
                    "severity": "warning",
                    "message": f"{symbol} exposure {weight:.1f}% exceeds {position_limit}% limit",
                }
            )
    for venue, value in venue_values.items():
        weight = value / total_market_value * 100
        if weight > venue_limit:
            alerts.append(
                {
                    "code": "VENUE_CONCENTRATION",
                    "severity": "warning",
                    "message": f"{venue} exposure {weight:.1f}% exceeds {venue_limit}% limit",
                }
            )
    for position in positions:
        if _d(position["unrealized_pnl_pct"]) < loss_limit:
            alerts.append(
                {
                    "code": "UNREALIZED_LOSS",
                    "severity": "warning",
                    "message": (
                        f"{position['symbol']} at {position['venue']} has "
                        f"{position['unrealized_pnl_pct']:.1f}% unrealized loss"
                    ),
                }
            )

    def weight_rows(values: dict[str, Decimal], key_name: str) -> list[dict[str, Any]]:
        return [
            {
                key_name: key,
                "market_value_usd": round(float(value), 2),
                "weight_pct": round(float(value / total_market_value * 100), 2),
            }
            for key, value in sorted(values.items(), key=lambda x: x[1], reverse=True)
        ]

    asset_weights = [float(value / total_market_value) for value in asset_values.values()]
    concentration_hhi = sum(weight**2 for weight in asset_weights)
    # HHI here uses 0–1 proportions: one asset yields 1; n equal assets yield 1/n.
    effective_asset_count = 1 / concentration_hhi
    biggest_asset = max(asset_values, key=asset_values.get)
    largest_weight_pct = float(asset_values[biggest_asset] / total_market_value * 100)

    scenarios = []
    shock_presets = [
        ("Broad market -5%", {asset: -5 for asset in asset_values}),
        ("Broad market -10%", {asset: -10 for asset in asset_values}),
        ("Broad market -20%", {asset: -20 for asset in asset_values}),
        ("BTC -20%, other prices unchanged", {"BTC": -20}),
        ("ETH -20%, other prices unchanged", {"ETH": -20}),
        ("SOL -20%, other prices unchanged", {"SOL": -20}),
        ("Broad market +10%", {asset: 10 for asset in asset_values}),
    ]
    for label, shocks in shock_presets:
        difference = sum(
            value * _d(shocks.get(asset, 0)) / 100
            for asset, value in asset_values.items()
        )
        scenarios.append(
            {
                "scenario": label,
                "portfolio_value_after_usd": round(float(total_market_value + difference), 2),
                "change_from_current_usd": round(float(difference), 2),
                "change_from_current_pct": round(float(difference / total_market_value * 100), 2),
            }
        )

    return {
        "mode": "DEMO / PAPER HOLDINGS — not connected to real accounts",
        "portfolio_label": portfolio["label"],
        "currency": "USD",
        "market_value_usd": round(float(total_market_value), 2),
        "cost_basis_usd": round(float(total_cost), 2),
        "unrealized_pnl_usd": round(float(total_market_value - total_cost), 2),
        "unrealized_pnl_pct": round(float((total_market_value / total_cost - 1) * 100), 2),
        "positions": positions,
        "by_asset": weight_rows(asset_values, "symbol"),
        "by_venue": weight_rows(venue_values, "venue"),
        "by_venue_type": weight_rows(venue_type_values, "venue_type"),
        "diversification": {
            "herfindahl_index": round(concentration_hhi, 4),
            "effective_number_of_assets": round(effective_asset_count, 2),
            "largest_asset": biggest_asset,
            "largest_asset_weight_pct": round(largest_weight_pct, 2),
            "interpretation": (
                "HHI sums squared current asset weights (0–1 scale); "
                "effective count is 1/HHI. Neither incorporates asset correlations."
            ),
        },
        "stress_scenarios": scenarios,
        "risk_policy": policy,
        "risk_status": "ALERT" if alerts else "WITHIN_DEMO_LIMITS",
        "alerts": alerts,
        "price_provenance_note": (
            "All synthetic venues and CEX/DEX positions are marked using Kraken Spot quotes. "
            "Venue labels do not represent connected balances or "
            "venue-specific execution prices."
        ),
        "accounting_note": (
            "Unrealized profit/loss only: current mark-to-market value minus "
            "hypothetical unit cost times quantity. Excludes fees, funding, taxes, "
            "realized trades, transfers and exchange balances."
        ),
    }
