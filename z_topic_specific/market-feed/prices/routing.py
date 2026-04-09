from django.urls import re_path
from .ws_consumers.price_feed import PriceFeedConsumer
from .ws_consumers.alerts import AlertConsumer

ws_urlpatterns = [
    re_path(r"ws/prices/(?P<asset>\w+)/$", PriceFeedConsumer.as_asgi()),
    re_path(r"ws/alerts/$", AlertConsumer.as_asgi()),
]
