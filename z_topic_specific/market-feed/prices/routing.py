from django.urls import re_path
from . import consumers

ws_urlpatterns = [
    re_path(r"ws/prices/(?P<asset>\w+)/$", consumers.PriceFeedConsumer.as_asgi()),
]
