from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import redis

from .models import Tick, AnalysisResult
from .serializers import TickSerializer, AnalysisResultSerializer

_redis = redis.from_url(settings.REDIS_URL)


class TickHistoryView(APIView):
    """
    GET /api/prices/<asset>/ticks/?limit=100
    Returns the most recent ticks for an asset, oldest-first so charts
    can plot them left-to-right without reversing on the client.
    """

    def get(self, request, asset: str):
        limit = min(int(request.query_params.get("limit", 100)), 500)
        ticks = (
            Tick.objects.filter(asset=asset.upper())
            .order_by("-timestamp")[:limit]
        )
        # Reverse so response is chronological
        data = TickSerializer(reversed(list(ticks)), many=True).data
        return Response(data)


class LatestPriceView(APIView):
    """
    GET /api/prices/<asset>/latest/
    Reads from Redis cache (TTL 60s). Returns 404 if no recent tick exists.
    Fast path — no DB hit.
    """

    def get(self, request, asset: str):
        key = f"price:{asset.upper()}"
        price = _redis.get(key)
        if price is None:
            return Response({"detail": "No recent price data."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"asset": asset.upper(), "price": price.decode()})


class AnalysisView(APIView):
    """
    GET /api/prices/<asset>/analysis/?limit=10
    Returns the most recent analysis results for an asset.
    Default limit=1 gives the latest snapshot; higher values give history.
    """

    def get(self, request, asset: str):
        limit = min(int(request.query_params.get("limit", 1)), 100)
        results = (
            AnalysisResult.objects.filter(asset=asset.upper())
            .order_by("-timestamp")[:limit]
        )
        data = AnalysisResultSerializer(results, many=True).data
        return Response(data)
