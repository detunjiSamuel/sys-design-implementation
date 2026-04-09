"""
Celery task: consumes raw_prices from Kafka and broadcasts to Django Channels layer.
Also writes each tick to PostgreSQL and caches latest price in Redis.
"""
import json
from datetime import datetime, timezone

import redis as redis_sync
from confluent_kafka import Consumer, KafkaError
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


def _make_consumer() -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": "price-consumer-group",
            # Start from earliest unread offset — replay on restart
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        }
    )


def _cache_latest_price(r: redis_sync.Redis, asset: str, price: str):
    """Store latest price in Redis with a 60s TTL."""
    r.setex(f"price:{asset}", 60, price)


def _broadcast(channel_layer, asset: str, payload: dict):
    """Push tick to all WebSocket clients subscribed to this asset."""
    async_to_sync(channel_layer.group_send)(
        f"prices_{asset}",
        {"type": "price_update", "data": payload},
    )


def _check_alerts(channel_layer, asset: str, price: float):
    """
    Fire any active alerts whose threshold has been crossed.
    Deactivates each alert after it fires so it triggers only once.
    """
    from prices.models import PriceAlert  # local import avoids circular at module load
    from prices.ws_consumers.alerts import ALERTS_GROUP

    active = PriceAlert.objects.filter(asset=asset, is_active=True)
    triggered_ids = []

    for alert in active:
        threshold = float(alert.threshold)
        hit = (alert.direction == PriceAlert.ABOVE and price >= threshold) or \
              (alert.direction == PriceAlert.BELOW and price <= threshold)
        if hit:
            triggered_ids.append(alert.id)
            async_to_sync(channel_layer.group_send)(
                ALERTS_GROUP,
                {
                    "type": "alert_triggered",
                    "data": {
                        "alert_id": alert.id,
                        "asset": asset,
                        "direction": alert.direction,
                        "threshold": str(alert.threshold),
                        "price": price,
                    },
                },
            )
            logger.info("Alert %d triggered: %s %s %s at %s", alert.id, asset, alert.direction, threshold, price)

    if triggered_ids:
        PriceAlert.objects.filter(id__in=triggered_ids).update(is_active=False)


@shared_task(bind=True, max_retries=None)
def run_kafka_consumer(self):
    """
    Polls Kafka for raw price ticks and fans out to:
      - Django Channels layer  (live WebSocket push)
      - PostgreSQL             (tick history)
      - Redis                  (latest price cache)
    """
    from prices.models import Tick  # local import avoids circular at module load

    consumer = _make_consumer()
    consumer.subscribe([settings.KAFKA_TOPIC_RAW_PRICES])

    channel_layer = get_channel_layer()
    r = redis_sync.from_url(settings.REDIS_URL)

    logger.info("Kafka consumer started, subscribed to %s", settings.KAFKA_TOPIC_RAW_PRICES)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("Kafka error: %s", msg.error())
                continue

            tick = json.loads(msg.value())
            asset = tick["asset"]
            price = tick["price"]
            ts = datetime.fromtimestamp(tick["timestamp"] / 1000, tz=timezone.utc)

            # 1. Persist to PostgreSQL
            Tick.objects.create(
                asset=asset,
                price=price,
                volume=tick["volume"],
                timestamp=ts,
            )

            # 2. Cache latest price in Redis
            _cache_latest_price(r, asset, price)

            # 3. Broadcast via Channels layer to WebSocket clients
            _broadcast(channel_layer, asset, {"asset": asset, "price": price, "timestamp": tick["timestamp"]})

            # 4. Check and fire any matching price alerts
            _check_alerts(channel_layer, asset, float(price))

    except Exception as exc:
        logger.exception("Kafka consumer error: %s", exc)
        consumer.close()
        raise self.retry(exc=exc, countdown=5)
