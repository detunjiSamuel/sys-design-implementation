"""
Pure functions for technical analysis. No Django imports — easily unit-testable.
All functions accept a pandas DataFrame with columns: [price, volume, timestamp].
"""
import pandas as pd


def sma(df: pd.DataFrame, period: int) -> float | None:
    """Simple Moving Average over the last `period` ticks."""
    if len(df) < period:
        return None
    return float(df["price"].iloc[-period:].mean())


def rsi(df: pd.DataFrame, period: int = 14) -> float | None:
    """
    Relative Strength Index.
    RSI = 100 - (100 / (1 + avg_gain / avg_loss))
    Returns None if not enough data.
    """
    if len(df) < period + 1:
        return None

    delta = df["price"].diff().dropna().iloc[-period:]
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.mean()
    avg_loss = losses.mean()

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def vwap(df: pd.DataFrame) -> float | None:
    """
    Volume-Weighted Average Price for the dataset window.
    VWAP = sum(price * volume) / sum(volume)
    """
    if df.empty or df["volume"].sum() == 0:
        return None
    return float((df["price"] * df["volume"]).sum() / df["volume"].sum())


def volatility(df: pd.DataFrame, period: int = 20) -> float | None:
    """Rolling standard deviation of price over `period` ticks."""
    if len(df) < period:
        return None
    return float(df["price"].iloc[-period:].std())
