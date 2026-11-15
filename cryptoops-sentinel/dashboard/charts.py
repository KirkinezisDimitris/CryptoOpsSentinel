"""Pure Plotly builders for common analyst-chart conventions; no Streamlit required."""
from __future__ import annotations

from typing import Literal

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PriceStyle = Literal["Candlestick", "OHLC", "Line", "Area"]
PRICE_STYLES = ("Candlestick", "OHLC", "Line", "Area")
ALLOCATION_STYLES = ("Donut", "Horizontal bars", "Treemap")
EQUITY_STYLES = ("Equity & drawdown", "Equity area", "Underwater drawdown")


def rsi_14(closes: pd.Series) -> pd.Series:
    """Match the API's simple-average RSI(14), including all-up / flat cases."""
    change = pd.to_numeric(closes).diff()
    gain = change.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-change.clip(upper=0)).rolling(14, min_periods=14).mean()
    result = 100 - (100 / (1 + gain / loss.replace(0, float("nan"))))
    result = result.mask((loss == 0) & (gain > 0), 100)
    return result.mask((loss == 0) & (gain == 0), 50)


def price_chart(
    frame: pd.DataFrame,
    symbol: str,
    period: str,
    style: PriceStyle = "Candlestick",
    show_volume: bool = True,
    show_rsi: bool = False,
    show_sma: bool = True,
) -> go.Figure:
    if style not in PRICE_STYLES:
        raise ValueError("Unsupported price-chart style")
    required = {"time", "open", "high", "low", "close", "volume_base", "sma_20", "sma_50"}
    if frame.empty or not required.issubset(frame):
        raise ValueError("Missing required OHLC fields")
    frame = frame.sort_values("time").copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    rows = 1 + int(show_volume) + int(show_rsi)
    heights = [0.68 if rows == 3 else 0.78 if rows == 2 else 1.0]
    if show_volume:
        heights.append(0.17 if rows == 3 else 0.22)
    if show_rsi:
        heights.append(0.15 if rows == 3 else 0.22)
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.035,
        row_heights=heights,
    )
    price_kwargs = dict(x=frame["time"], open=frame["open"], high=frame["high"],
                        low=frame["low"], close=frame["close"], name=f"{symbol}/USD")
    if style == "Candlestick":
        fig.add_trace(go.Candlestick(**price_kwargs), row=1, col=1)
    elif style == "OHLC":
        fig.add_trace(go.Ohlc(**price_kwargs), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(
            x=frame["time"], y=frame["close"], name=f"{symbol} close",
            mode="lines+markers", marker={"size": 3},
            fill="tozeroy" if style == "Area" else None,
        ), row=1, col=1)
    if show_sma:
        for length in (20, 50):
            fig.add_trace(go.Scatter(
                x=frame["time"], y=frame[f"sma_{length}"], mode="lines",
                name=f"SMA {length}", line={"width": 1.5},
            ), row=1, col=1)
    fig.update_yaxes(title_text="Price (USD)", row=1, col=1, showspikes=True)
    subrow = 2
    if show_volume:
        colors = ["#25a87a" if c >= o else "#d65f69" for o, c in zip(frame["open"], frame["close"])]
        fig.add_trace(go.Bar(x=frame["time"], y=frame["volume_base"],
                             marker_color=colors, name="Traded volume (base units)"),
                      row=subrow, col=1)
        fig.update_yaxes(title_text="Volume", row=subrow, col=1)
        subrow += 1
    if show_rsi:
        rsi = rsi_14(frame["close"])
        fig.add_trace(go.Scatter(x=frame["time"], y=rsi, name="RSI (14)",
                                 mode="lines", line={"width": 1.5}), row=subrow, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#d65f69", row=subrow, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#25a87a", row=subrow, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=subrow, col=1)
    fig.update_layout(
        title=f"{symbol}/USD · {period} · {style}", height=650 if rows == 3 else 565 if rows == 2 else 460,
        margin=dict(l=12, r=12, t=50, b=10), hovermode="x unified",
        legend=dict(orientation="h", y=1.06, x=0),
        uirevision=f"{symbol}-{period}-{style}",
    )
    fig.update_xaxes(rangeslider_visible=False, showspikes=True, spikemode="across")
    return fig


def allocation_chart(assets: pd.DataFrame, style: str = "Donut") -> go.Figure:
    if style not in ALLOCATION_STYLES:
        raise ValueError("Unsupported allocation-chart style")
    if assets.empty or not {"symbol", "market_value_usd", "weight_pct"}.issubset(assets):
        raise ValueError("Missing asset exposures")
    if style == "Donut":
        fig = go.Figure(go.Pie(labels=assets["symbol"], values=assets["market_value_usd"],
                               hole=0.55, textinfo="label+percent"))
    elif style == "Horizontal bars":
        ordered = assets.sort_values("weight_pct")
        fig = go.Figure(go.Bar(x=ordered["weight_pct"], y=ordered["symbol"],
                               orientation="h", text=ordered["weight_pct"],
                               texttemplate="%{text:.2f}%", textposition="auto"))
        fig.update_xaxes(title_text="Weight (%)", range=[0, 100])
    else:
        fig = go.Figure(go.Treemap(labels=assets["symbol"],
                                   parents=[""] * len(assets),
                                   values=assets["market_value_usd"],
                                   textinfo="label+percent root"))
    fig.update_layout(title=f"Asset allocation · {style}", height=370,
                      margin=dict(l=10, r=10, t=50, b=10))
    return fig


def equity_chart(history: pd.DataFrame, style: str = "Equity & drawdown") -> go.Figure:
    if style not in EQUITY_STYLES:
        raise ValueError("Unsupported equity-chart style")
    if history.empty or not {"date_utc", "synthetic_buy_hold_value_usd", "drawdown_pct"}.issubset(history):
        raise ValueError("Missing historical portfolio values")
    times = pd.to_datetime(history["date_utc"], utc=True)
    if style == "Equity & drawdown":
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28],
                            vertical_spacing=0.06)
        fig.add_trace(go.Scatter(x=times, y=history["synthetic_buy_hold_value_usd"],
                                 mode="lines", name="Hypothetical portfolio value"), row=1, col=1)
        fig.add_trace(go.Scatter(x=times, y=history["drawdown_pct"], name="Drawdown",
                                 fill="tozeroy", mode="lines"), row=2, col=1)
        fig.update_yaxes(title_text="Portfolio (USD)", row=1, col=1)
        fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)
    elif style == "Underwater drawdown":
        fig = go.Figure(go.Scatter(x=times, y=history["drawdown_pct"],
                                   name="Drawdown", fill="tozeroy", mode="lines"))
        fig.update_yaxes(title_text="Drawdown (%)")
    else:
        fig = go.Figure(go.Scatter(x=times, y=history["synthetic_buy_hold_value_usd"],
                                   name="Hypothetical portfolio value", fill="tozeroy",
                                   mode="lines"))
        fig.update_yaxes(title_text="Portfolio (USD)")
    fig.update_layout(title=f"Retrospective fictional buy-and-hold · {style}",
                      height=460, hovermode="x unified",
                      margin=dict(l=10, r=10, t=50, b=10))
    return fig
