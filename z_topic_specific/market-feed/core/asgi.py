import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Import ws_urlpatterns after Django setup
django_asgi_app = get_asgi_application()

from prices.routing import ws_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(ws_urlpatterns),
    }
)
