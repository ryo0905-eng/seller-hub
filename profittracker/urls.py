from django.urls import path

from . import views


urlpatterns = [
    path("", views.ProductListView.as_view(), name="product_list"),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    path("api/exchange-rate/", views.exchange_rate_api, name="exchange_rate_api"),
    path("products/new/", views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/delete/", views.ProductDeleteView.as_view(), name="product_delete"),
]
