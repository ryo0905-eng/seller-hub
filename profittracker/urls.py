from django.urls import path

from . import views


urlpatterns = [
    path("", views.ProductListView.as_view(), name="product_list"),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    path("simulator/", views.SourcingSimulatorView.as_view(), name="sourcing_simulator"),
    path("settings/", views.SellerSettingsView.as_view(), name="seller_settings"),
    path("api/exchange-rate/", views.exchange_rate_api, name="exchange_rate_api"),
    path("products/import/", views.ProductCsvImportView.as_view(), name="product_import"),
    path("products/export/", views.ProductCsvExportView.as_view(), name="product_export"),
    path("products/new/", views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("products/<int:pk>/quick-update/", views.ProductQuickUpdateView.as_view(), name="product_quick_update"),
    path("products/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/delete/", views.ProductDeleteView.as_view(), name="product_delete"),
]
