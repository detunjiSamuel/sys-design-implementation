from django.urls import path
from .views import TickHistoryView, LatestPriceView, AnalysisView

urlpatterns = [
    path("<str:asset>/ticks/", TickHistoryView.as_view()),
    path("<str:asset>/latest/", LatestPriceView.as_view()),
    path("<str:asset>/analysis/", AnalysisView.as_view()),
]
