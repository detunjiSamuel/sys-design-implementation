"""
Celery task: opens a Binance WebSocket and publishes raw price ticks to Kafka.
Runs indefinitely inside a Celery worker process.
"""
import json
import asyncio
import websockets
from confluent_kafka import Producer
from django.conf import settings
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://stream.binance.com:9443/stream"


def _make_producer() -> Producer:
    return Producer({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})


def _delivery_report(err, msg):
    if err:
        logger.error("Kafka delivery failed: %s", err)


async def _stream(assets: list[str]):
    """Connect to Binance combined stream and forward ticks to Kafka."""
    producer = _make_producer()
    streams = "/".join(f"{a.lower()}@trade" for a in assets)
    url = f"{BINANCE_WS_URL}?streams={streams}"

    async with websockets.connect(url) as ws:
        logger.info("Connected to Binance WS: %s", url)
        async for raw in ws:
            data = json.loads(raw)
            trade = data["data"]

            tick = {
                "asset": trade["s"],       # e.g. "BTCUSDT"
                "price": trade["p"],       # trade price (string from Binance)
                "volume": trade["q"],      # trade quantity
                "timestamp": trade["T"],   # trade time (ms epoch)
            }

            producer.produce(
                settings.KAFKA_TOPIC_RAW_PRICES,
                key=tick["asset"],
                value=json.dumps(tick),
                callback=_delivery_report,
            )
            producer.poll(0)  # trigger delivery callbacks without blocking


@shared_task(bind=True, max_retries=None)
def run_binance_ws(self, assets: list[str] | None = None):
    """
    Entry point called by Celery worker.
    Runs the async WS loop synchronously via asyncio.run().
    Retries on any connection error.
    """
    assets = assets or ["BTCUSDT", "ETHUSDT"]
    try:
        asyncio.run(_stream(assets))
    except Exception as exc:
        logger.exception("Binance WS error, retrying: %s", exc)
        raise self.retry(exc=exc, countdown=5)
