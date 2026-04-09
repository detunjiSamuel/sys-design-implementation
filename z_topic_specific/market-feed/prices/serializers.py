from rest_framework import serializers
from .models import Tick, AnalysisResult, PriceAlert, MarketSentiment


class TickSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tick
        fields = ["asset", "price", "volume", "timestamp"]


class AnalysisResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisResult
        fields = ["asset", "timestamp", "sma_20", "sma_50", "rsi_14", "vwap", "volatility"]


class PriceAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceAlert
        fields = ["id", "asset", "threshold", "direction", "is_active", "created_at"]
        read_only_fields = ["id", "is_active", "created_at"]


class MarketSentimentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketSentiment
        fields = ["id", "asset", "timestamp", "reddit_posts", "analysis"]
