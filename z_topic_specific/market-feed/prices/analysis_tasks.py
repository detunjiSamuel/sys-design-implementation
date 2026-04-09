"""
Celery tasks triggered by Beat to compute and persist analysis results.
"""
import logging
from datetime import datetime, timezone

import pandas as pd
from celery import shared_task
from django.utils import timezone as dj_timezone

from prices.models import Tick, AnalysisResult
from prices import analysis

logger = logging.getLogger(__name__)

ASSETS = ["BTCUSDT", "ETHUSDT"]
# How many ticks to load per asset. RSI needs 15+, SMA-50 needs 50+.
LOOKBACK = 200


def _load_ticks(asset: str) -> pd.DataFrame:
    """Fetch the most recent LOOKBACK ticks from Postgres as a DataFrame."""
    qs = (
        Tick.objects.filter(asset=asset)
        .order_by("-timestamp")[:LOOKBACK]
        .values("price", "volume", "timestamp")
    )
    df = pd.DataFrame(list(qs))
    if df.empty:
        return df
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["price"] = df["price"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df


@shared_task
def compute_analysis(asset: str):
    """
    Compute all indicators for one asset and save an AnalysisResult row.
    Idempotent: running twice on the same data produces the same result.
    """
    df = _load_ticks(asset)
    if df.empty:
        logger.warning("No tick data for %s, skipping analysis", asset)
        return

    now = dj_timezone.now()

    AnalysisResult.objects.create(
        asset=asset,
        timestamp=now,
        sma_20=analysis.sma(df, 20),
        sma_50=analysis.sma(df, 50),
        rsi_14=analysis.rsi(df, 14),
        vwap=analysis.vwap(df),
        volatility=analysis.volatility(df, 20),
    )
    logger.info("Analysis saved for %s at %s", asset, now)


@shared_task
def run_all_analysis():
    """
    Fan out compute_analysis to all tracked assets.
    This is what Beat calls on schedule.
    """
    for asset in ASSETS:
        compute_analysis.delay(asset)
