from django.urls import path
from tender_search.views import (
    dashboard_clear_logs_view,
    dashboard_home,
    dashboard_logs_view,
    gem_bid_results_view,
<<<<<<< HEAD
    search_tender_view,
    sync_result_view,
=======
>>>>>>> 6f771f683b6d6658d06eb78b0dea8c913fd9f33d
    worker_status_view,
    worker_toggle_view,
)

urlpatterns = [
    path("", dashboard_home),
    path("api/gem-bid-results/", gem_bid_results_view),
    path("api/dashboard/status/", worker_status_view),
    path("api/dashboard/worker/<str:worker>/<str:action>/", worker_toggle_view),
    path("api/dashboard/logs/", dashboard_logs_view),
    path("api/dashboard/logs/clear/", dashboard_clear_logs_view),
    path("api/v1/sync-result/", sync_result_view),
]
