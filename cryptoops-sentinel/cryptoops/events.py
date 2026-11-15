"""Descriptive market changes around a selected calendar date; no causal inference."""
from __future__ import annotations

from datetime import date
from typing import Any


def event_window(candles: list[dict[str, Any]], selected: date) -> dict[str, Any]:
    closes = {date.fromisoformat(row["time"][:10]): float(row["close"]) for row in candles}
    current = closes.get(selected)
    previous = closes.get(date.fromordinal(selected.toordinal() - 1))
    following = closes.get(date.fromordinal(selected.toordinal() + 1))

    def pct(start: float | None, end: float | None) -> float | None:
        if start is None or end is None or start <= 0:
            return None
        return round((end / start - 1) * 100, 3)

    nearby = [
        {"date_utc": day.isoformat(), "completed_close_usd": price}
        for day, price in sorted(closes.items())
        if abs((day - selected).days) <= 3
    ]
    return {
        "selected_date_utc": selected.isoformat(),
        "surrounding_completed_daily_closes": nearby,
        "previous_completed_close_usd": previous,
        "selected_completed_close_usd": current,
        "next_completed_close_usd": following,
        "previous_to_selected_day_pct": pct(previous, current),
        "selected_to_next_day_pct": pct(current, following),
        "observations_available": current is not None,
        "methodology": (
            "Adjacent completed UTC daily closes from Kraken Spot. A 24h interval's close may "
            "precede or follow individual news publication. The GDELT time is first-seen, "
            "not necessarily publication. These values only document co-movement and "
            "CANNOT establish that any headline caused a price change. "
            "Missing dates or unfinished days return null."
        ),
    }
