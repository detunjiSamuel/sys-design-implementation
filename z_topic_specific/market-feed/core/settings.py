from decouple import config

SECRET_KEY = config("SECRET_KEY", default="dev-secret-key")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "channels",
    "django_celery_beat",
    "prices.apps.PricesConfig",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

# --- Database ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="marketfeed"),
        "USER": config("DB_USER", default="mf"),
        "PASSWORD": config("DB_PASSWORD", default="mf"),
        "HOST": config("DB_HOST", default="postgres"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# --- Redis / Channels ---
REDIS_URL = config("REDIS_URL", default="redis://redis:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# --- Celery ---
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "run-analysis-every-minute": {
        "task": "prices.analysis_tasks.run_all_analysis",
        "schedule": 60.0,
    },
    "run-sentiment-every-15-minutes": {
        "task": "prices.sentiment_tasks.run_all_sentiment",
        "schedule": crontab(minute="*/15"),
    },
}

# --- OpenAI ---
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")

# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS = config("KAFKA_BOOTSTRAP_SERVERS", default="kafka:9092")
KAFKA_TOPIC_RAW_PRICES = "raw_prices"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
