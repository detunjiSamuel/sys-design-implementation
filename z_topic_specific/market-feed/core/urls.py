from django.urls import path, include

urlpatterns = [
    path("api/prices/", include("prices.urls")),
]
