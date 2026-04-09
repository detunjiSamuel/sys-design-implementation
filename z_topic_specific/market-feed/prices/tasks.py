"""
Re-exports all tasks so Celery's autodiscover finds them in one place.
"""
from .kafka_producer import run_binance_ws  # noqa: F401
from .kafka_consumer import run_kafka_consumer  # noqa: F401
from .analysis_tasks import run_all_analysis, compute_analysis  # noqa: F401
