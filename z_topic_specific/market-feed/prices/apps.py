from django.apps import AppConfig


class PricesConfig(AppConfig):
    name = "prices"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Kick off the long-running tasks when the Celery worker starts.
        # The worker_ready signal fires once the worker is fully initialized.
        from celery.signals import worker_ready

        @worker_ready.connect
        def on_worker_ready(sender, **kwargs):
            from prices.tasks import run_binance_ws, run_kafka_consumer
            run_binance_ws.delay()
            run_kafka_consumer.delay()
