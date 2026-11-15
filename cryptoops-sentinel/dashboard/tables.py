"""Human-facing labels and always-visible, immediately adjacent table explanations.

API schemas stay stable; formatting is a view-layer concern.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

# API field -> (UI title, business definition, main factor affecting the value).
FIELDS: dict[str, tuple[str, str, str]] = {
    "symbol": ("Asset", "Ticker identifying the cryptocurrency.", "The chosen instrument."),
    "venue": ("Trading Venue", "Exchange/DEX label for a hypothetical holding.", "Portfolio configuration; balances are not verified."),
    "venue_type": ("Venue Type", "CEX is centralized; DEX is decentralized.", "Portfolio configuration."),
    "quantity": ("Units Held", "Hypothetical number of coins held.", "Configured demo holdings."),
    "unit_cost_usd": ("Entry Price (USD)", "Assumed acquisition cost per coin.", "Configured demo cost basis."),
    "live_price_usd": ("Market Price (USD)", "Current available Kraken spot quote per coin.", "Trading and quote freshness."),
    "market_value_usd": ("Market Value (USD)", "Units held multiplied by the spot price.", "Price and holding quantity."),
    "unrealized_pnl_usd": ("Unrealized P&L (USD)", "Market value minus fictional acquisition cost.", "Market price, size and cost basis."),
    "unrealized_pnl_pct": ("Unrealized P&L (%)", "Unrealized profit/loss divided by cost basis.", "Market price and assumed entry price."),
    "weight_pct": ("Portfolio Weight (%)", "Share of total current portfolio value.", "Relative values of all assets."),
    "portfolio_value_after_usd": ("Stressed Value (USD)", "Hypothetical portfolio value after the specified price shock.", "Current marks and shock assumptions."),
    "change_from_current_usd": ("Change vs. Now (USD)", "Scenario portfolio value minus its present value.", "Scenario magnitude and current asset weights."),
    "change_from_current_pct": ("Change vs. Now (%)", "Scenario change expressed relative to current total value.", "Scenario magnitude and portfolio composition."),
    "scenario": ("Stress Scenario", "Hypothetical change applied to prices.", "Preset scenario assumptions."),
    "scenario_name": ("Stress Scenario", "Hypothetical change applied to prices.", "Preset scenario assumptions."),
    "projected_market_value_usd": ("Stressed Value (USD)", "Portfolio value after assumed price shocks.", "Scenario and current marks."),
    "stressed_market_value_usd": ("Stressed Value (USD)", "Portfolio value after assumed price shocks.", "Scenario and current marks."),
    "projected_pnl_usd": ("Stressed P&L (USD)", "Estimated change under the applied shock.", "Current value and shock magnitude."),
    "portfolio_change_usd": ("Portfolio Change (USD)", "Simulated change in portfolio value.", "Scenario assumptions."),
    "portfolio_change_pct": ("Portfolio Change (%)", "Simulated percentage change to portfolio.", "Scenario assumptions."),
    "loss_usd": ("Scenario Loss (USD)", "Simulated USD loss in the stress case.", "Scenario magnitude and position sizing."),
    "annualized_volatility_pct": ("Annualized Volatility (%)", "Historical return dispersion scaled to one year.", "Sample duration and return variability."),
    "period_return_pct": ("Sample Return (%)", "Start-to-end price change over the observed window.", "Selected date window and price changes."),
    "latest_price_usd": ("Latest Price (USD)", "Last available price per asset.", "Market conditions and data latency."),
    "latest_at_utc": ("Latest Observation (UTC)", "Timestamp of latest stored observation.", "Ingestion schedule and feed connectivity."),
    "observed_at_utc": ("Observed At (UTC)", "Timestamp of latest recorded observation.", "Ingestion schedule and feed connectivity."),
    "age_seconds": ("Snapshot Age (sec)", "Seconds since latest stored observation.", "Ingestion schedule and feed delays."),
    "snapshot_count": ("Snapshot Records", "Number of observations retained for the asset.", "Ingestion frequency."),
    "last_snapshot_utc": ("Last Observation (UTC)", "Timestamp of most recent stored snapshot.", "Ingestion runtime and connectivity."),
    "status": ("Data Status", "Whether the recorded data is considered fresh.", "Age and configured freshness threshold."),
    "source": ("Data Source", "System supplying the observation.", "Active feed and fallback path."),
    "last_ingested_at_utc": ("Last Ingestion (UTC)", "UTC time when the latest persisted snapshot was captured.", "Ingestion execution time."),
    "last_stored_price_usd": ("Stored Price (USD)", "Spot quote captured at the last persisted ingestion.", "Previous observation; may be older than live quotes."),
    "metric": ("Signal Indicator", "Technical factor evaluated in the directional rubric.", "The underlying close, SMA and RSI values."),
    "interpretation": ("Signal Interpretation", "Reason a technical factor contributes its points.", "Indicator values and the configured rubric."),
    "points": ("Signal Contribution", "Points added or subtracted from the neutral technical score.", "Indicator conditions."),
    "factor": ("Signal Factor", "Rule evaluated in the technical rubric.", "Chosen technical indicator."),
    "reason": ("Rationale", "Plain-language explanation of the factor result.", "Observed indicator relationships."),
}


def present_table(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, str, str]]]:
    """Return a display-only renamed copy and definitions in displayed order."""
    renamed: dict[str, str] = {}
    descriptions: list[tuple[str, str, str]] = []
    for col in frame.columns:
        if col in FIELDS:
            name, meaning, driver = FIELDS[col]
        elif col.isupper() and len(col) <= 6:  # correlation-matrix ticker columns
            name, meaning, driver = f"{col} Correlation", (
                f"Historical daily-return correlation to {col} (−1 to +1)."), (
                "Both assets’ observed return series and sample dates.")
        else:
            name = col.replace("_", " ").strip().title()
            meaning = "Recorded value reported by the analytical API."
            driver = "Source data and the calculation methodology."
        renamed[col] = name
        descriptions.append((name, meaning, driver))
    return frame.rename(columns=renamed).copy(), descriptions


def show_table(frame: pd.DataFrame, st: Any, *, note: str | None = None) -> None:
    """The explanations remain visibly attached immediately below every rendered table."""
    if frame.empty:
        st.info("No rows available for this table.")
        return
    display, descriptions = present_table(frame)
    formats = {}
    for col in display.columns:
        if pd.api.types.is_numeric_dtype(display[col]):
            if "(USD)" in col:
                formats[col] = st.column_config.NumberColumn(col, format="$%.2f")
            elif "(%)" in col:
                formats[col] = st.column_config.NumberColumn(col, format="%.2f%%")
            elif col == "Units Held":
                formats[col] = st.column_config.NumberColumn(col, format="%.6f")
    st.dataframe(display, column_config=formats, use_container_width=True, hide_index=True)
    st.markdown("**Column terminology**")
    st.caption("  |  ".join(f"**{name}:** {meaning} Affected by: {driver}"
                           for name, meaning, driver in descriptions))
    if note:
        st.caption(note)
