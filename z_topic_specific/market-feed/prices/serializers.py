from rest_framework import serializers
from .models import Tick, AnalysisResult


class TickSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tick
        fields = ["asset", "price", "volume", "timestamp"]


class AnalysisResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisResult
        fields = ["asset", "timestamp", "sma_20", "sma_50", "rsi_14", "vwap", "volatility"]
