"""
Celery task that fetches Reddit posts, runs OpenAI analysis, and saves a MarketSentiment row.
Beat fires this every 15 minutes per tracked asset.
"""
import logging

from celery import shared_task
from django.conf import settings

from prices import sentiment as sentiment_lib
from prices.models import MarketSentiment

logger = logging.getLogger(__name__)

ASSETS = ["BTCUSDT", "ETHUSDT"]


@shared_task
def run_market_analysis(asset: str):
    """
    1. Fetch top Reddit posts for `asset`.
    2. Send them to OpenAI for sentiment analysis.
    3. Persist a MarketSentiment row.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        logger.error("OPENAI_API_KEY not configured — skipping sentiment for %s", asset)
        return

    posts = sentiment_lib.fetch_reddit_posts(asset)
    logger.info("Fetched %d Reddit posts for %s", len(posts), asset)

    analysis_text = sentiment_lib.analyse_sentiment(asset, posts, api_key)
    logger.info("OpenAI analysis for %s: %s", asset, analysis_text[:80])

    MarketSentiment.objects.create(
        asset=asset.upper(),
        reddit_posts=posts,
        analysis=analysis_text,
    )
    logger.info("MarketSentiment saved for %s", asset)


@shared_task
def run_all_sentiment():
    """Fan out run_market_analysis to all tracked assets. Called by Beat."""
    for asset in ASSETS:
        run_market_analysis.delay(asset)
