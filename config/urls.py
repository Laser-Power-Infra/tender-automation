from django.urls import path
from tender_search.views import gem_bid_results_view, search_tender_view

urlpatterns = [
    path("api/search-tender/", search_tender_view),
    path("api/gem-bid-results/", gem_bid_results_view),
]
