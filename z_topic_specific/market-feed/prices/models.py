from django.db import models


class PriceAlert(models.Model):
    """A threshold-based alert registered by a client."""

    ABOVE = "above"
    BELOW = "below"
    DIRECTION_CHOICES = [(ABOVE, "Above"), (BELOW, "Below")]

    asset = models.CharField(max_length=20)
    threshold = models.DecimalField(max_digits=20, decimal_places=8)
    direction = models.CharField(max_length=5, choices=DIRECTION_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["asset", "is_active"])]

    def __str__(self):
        return f"{self.asset} {self.direction} {self.threshold} (active={self.is_active})"


class MarketSentiment(models.Model):
    """OpenAI-generated sentiment analysis over recent Reddit posts."""

    asset = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)
    reddit_posts = models.JSONField()          # list of post titles/scores fetched
    analysis = models.TextField()              # free-text summary from OpenAI

    class Meta:
        indexes = [models.Index(fields=["asset", "timestamp"])]

    def __str__(self):
        return f"{self.asset} sentiment @ {self.timestamp}"


class Tick(models.Model):
    """Raw price tick received from Binance."""

    asset = models.CharField(max_length=20)  # e.g. "BTCUSDT"
    price = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["asset", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.asset} {self.price} @ {self.timestamp}"


class AnalysisResult(models.Model):
    """Computed indicators for a given asset and window."""

    asset = models.CharField(max_length=20)
    timestamp = models.DateTimeField()
    sma_20 = models.FloatField(null=True)
    sma_50 = models.FloatField(null=True)
    rsi_14 = models.FloatField(null=True)
    vwap = models.FloatField(null=True)
    volatility = models.FloatField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=["asset", "timestamp"]),
        ]
