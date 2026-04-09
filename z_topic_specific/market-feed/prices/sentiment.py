"""
Pure functions for market sentiment analysis. No Django imports.

fetch_reddit_posts  — scrapes recent posts from Reddit's public JSON API
analyse_sentiment   — sends post titles to OpenAI and returns a plain-text summary
"""
import logging
from typing import Any

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

# Map asset symbol → subreddit(s) to search
_ASSET_SUBREDDITS: dict[str, list[str]] = {
    "BTCUSDT": ["Bitcoin", "CryptoCurrency"],
    "ETHUSDT": ["ethereum", "CryptoCurrency"],
}
_DEFAULT_SUBREDDITS = ["CryptoCurrency"]

_REDDIT_HEADERS = {"User-Agent": "MarketFeed/1.0 (sentiment-bot)"}


def fetch_reddit_posts(asset: str, limit: int = 25) -> list[dict[str, Any]]:
    """
    Return up to `limit` recent hot posts mentioning the asset.
    Uses Reddit's unauthenticated JSON endpoint — no credentials required.
    Each item: {"title": str, "score": int, "url": str}
    """
    subreddits = _ASSET_SUBREDDITS.get(asset.upper(), _DEFAULT_SUBREDDITS)
    posts: list[dict[str, Any]] = []

    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
        try:
            resp = requests.get(url, headers=_REDDIT_HEADERS, timeout=10)
            resp.raise_for_status()
            children = resp.json()["data"]["children"]
            for child in children:
                d = child["data"]
                posts.append({"title": d["title"], "score": d["score"], "url": d["url"]})
        except Exception as exc:
            logger.warning("Reddit fetch failed for r/%s: %s", sub, exc)

    # Deduplicate by title, keep highest score
    seen: dict[str, dict] = {}
    for p in posts:
        key = p["title"]
        if key not in seen or p["score"] > seen[key]["score"]:
            seen[key] = p

    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:limit]


def analyse_sentiment(asset: str, posts: list[dict[str, Any]], api_key: str) -> str:
    """
    Send post titles to OpenAI and return a concise sentiment summary.
    Raises on API errors — callers should handle exceptions.
    """
    if not posts:
        return "No Reddit posts found for sentiment analysis."

    titles = "\n".join(f"- {p['title']} (score: {p['score']})" for p in posts)
    prompt = (
        f"You are a crypto market analyst. Based on the following recent Reddit posts about {asset}, "
        f"summarise the current market sentiment in 2-3 sentences. "
        f"Classify it as Bullish, Bearish, or Neutral and explain why.\n\n"
        f"Posts:\n{titles}"
    )

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()
