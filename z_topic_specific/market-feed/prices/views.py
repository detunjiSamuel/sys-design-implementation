from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import redis

from .models import Tick, AnalysisResult, PriceAlert, MarketSentiment
from .serializers import TickSerializer, AnalysisResultSerializer, PriceAlertSerializer, MarketSentimentSerializer

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


class PriceAlertListCreateView(APIView):
    """
    GET  /api/prices/alerts/        — list all active alerts
    POST /api/prices/alerts/        — create a new alert
        body: { "asset": "BTCUSDT", "threshold": "70000", "direction": "above" }
    """

    def get(self, request):
        alerts = PriceAlert.objects.filter(is_active=True).order_by("-created_at")
        return Response(PriceAlertSerializer(alerts, many=True).data)

    def post(self, request):
        serializer = PriceAlertSerializer(data=request.data)
        if serializer.is_valid():
            alert = serializer.save(asset=serializer.validated_data["asset"].upper())
            return Response(PriceAlertSerializer(alert).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PriceAlertDetailView(APIView):
    """
    DELETE /api/prices/alerts/<pk>/  — deactivate an alert
    """

    def delete(self, request, pk: int):
        try:
            alert = PriceAlert.objects.get(pk=pk)
        except PriceAlert.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        alert.is_active = False
        alert.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MarketSentimentView(APIView):
    """
    GET /api/prices/<asset>/sentiment/?limit=1
    Returns the most recent sentiment analysis for an asset.
    """

    def get(self, request, asset: str):
        limit = min(int(request.query_params.get("limit", 1)), 20)
        results = (
            MarketSentiment.objects.filter(asset=asset.upper())
            .order_by("-timestamp")[:limit]
        )
        if not results:
            return Response({"detail": "No sentiment data yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(MarketSentimentSerializer(results, many=True).data)
