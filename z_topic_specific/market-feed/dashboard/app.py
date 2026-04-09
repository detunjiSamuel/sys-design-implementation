import time
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_BASE = "http://django:8000/api/prices"

st.set_page_config(page_title="Market Feed", layout="wide")

# --- Sidebar ---
st.sidebar.title("Settings")
asset = st.sidebar.selectbox("Asset", ["BTCUSDT", "ETHUSDT"])
tick_limit = st.sidebar.slider("Ticks to display", 50, 500, 100, step=50)
refresh_interval = st.sidebar.slider("Refresh interval (s)", 5, 60, 10)

st.title(f"Market Feed — {asset}")


# --- Data fetching ---
def fetch_ticks(asset: str, limit: int) -> pd.DataFrame:
    try:
        r = requests.get(f"{API_BASE}/{asset}/ticks/", params={"limit": limit}, timeout=3)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["price"] = df["price"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return df
    except Exception:
        return pd.DataFrame()


def fetch_latest(asset: str) -> str | None:
    try:
        r = requests.get(f"{API_BASE}/{asset}/latest/", timeout=2)
        if r.status_code == 200:
            return r.json()["price"]
    except Exception:
        pass
    return None


def fetch_analysis(asset: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/{asset}/analysis/", params={"limit": 1}, timeout=2)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None


# --- Layout placeholders ---
price_placeholder = st.empty()
col1, col2, col3, col4, col5 = st.columns(5)
metric_sma20 = col1.empty()
metric_sma50 = col2.empty()
metric_rsi = col3.empty()
metric_vwap = col4.empty()
metric_vol = col5.empty()
chart_placeholder = st.empty()
volume_placeholder = st.empty()


def fmt(val, decimals=2):
    return f"{val:.{decimals}f}" if val is not None else "—"


# --- Main loop ---
while True:
    latest = fetch_latest(asset)
    ticks = fetch_ticks(asset, tick_limit)
    analysis = fetch_analysis(asset)

    # Current price
    price_placeholder.metric(
        label="Current Price",
        value=f"${float(latest):,.2f}" if latest else "No data",
    )

    # Indicator metrics
    if analysis:
        metric_sma20.metric("SMA 20", fmt(analysis.get("sma_20")))
        metric_sma50.metric("SMA 50", fmt(analysis.get("sma_50")))
        metric_rsi.metric("RSI 14", fmt(analysis.get("rsi_14")))
        metric_vwap.metric("VWAP", fmt(analysis.get("vwap")))
        metric_vol.metric("Volatility", fmt(analysis.get("volatility"), 4))

    # Price chart with SMA overlays
    if not ticks.empty:
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=ticks["timestamp"], y=ticks["price"],
            mode="lines", name="Price",
            line=dict(color="#00b4d8", width=1.5),
        ))

        # SMA overlays if we have enough data
        if analysis and analysis.get("sma_20"):
            ticks["sma_20"] = ticks["price"].rolling(20).mean()
            ticks["sma_50"] = ticks["price"].rolling(50).mean()
            fig.add_trace(go.Scatter(
                x=ticks["timestamp"], y=ticks["sma_20"],
                mode="lines", name="SMA 20",
                line=dict(color="#f77f00", width=1, dash="dot"),
            ))
            fig.add_trace(go.Scatter(
                x=ticks["timestamp"], y=ticks["sma_50"],
                mode="lines", name="SMA 50",
                line=dict(color="#d62828", width=1, dash="dot"),
            ))

        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", y=1.1),
            xaxis_title=None,
            yaxis_title="Price (USDT)",
            template="plotly_dark",
        )
        chart_placeholder.plotly_chart(fig, use_container_width=True)

        # Volume bar chart
        vol_fig = go.Figure(go.Bar(
            x=ticks["timestamp"], y=ticks["volume"],
            marker_color="#48cae4", name="Volume",
        ))
        vol_fig.update_layout(
            height=150,
            margin=dict(l=0, r=0, t=10, b=0),
            template="plotly_dark",
            showlegend=False,
        )
        volume_placeholder.plotly_chart(vol_fig, use_container_width=True)

    time.sleep(refresh_interval)
    st.rerun()
