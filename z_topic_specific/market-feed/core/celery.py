import os
from celery import Celery
from celery.signals import worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """Auto-start the long-running Kafka producer and consumer on worker boot."""
    app.send_task("prices.kafka_producer.run_binance_ws")
    app.send_task("prices.kafka_consumer.run_kafka_consumer")
