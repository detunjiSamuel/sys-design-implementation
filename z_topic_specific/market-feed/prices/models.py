from django.db import models


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
