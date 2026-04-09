from django.urls import path
from .views import (
    TickHistoryView,
    LatestPriceView,
    AnalysisView,
    PriceAlertListCreateView,
    PriceAlertDetailView,
    MarketSentimentView,
)

urlpatterns = [
    path("<str:asset>/ticks/", TickHistoryView.as_view()),
    path("<str:asset>/latest/", LatestPriceView.as_view()),
    path("<str:asset>/analysis/", AnalysisView.as_view()),
    path("<str:asset>/sentiment/", MarketSentimentView.as_view()),
    path("alerts/", PriceAlertListCreateView.as_view()),
    path("alerts/<int:pk>/", PriceAlertDetailView.as_view()),
]
