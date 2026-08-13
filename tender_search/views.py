from rest_framework.decorators import api_view
from rest_framework.response import Response
from .services.nic_tender import search_tender
from .services.gem_bid_results import extract_bid_results


@api_view(["POST"])
def search_tender_view(request):
    website = request.data.get("website")
    reference_no = request.data.get("reference_no")
    if not website or not reference_no:
        return Response(
            {"error": "website and reference_no are required"},
            status=400,
        )
    result = search_tender(website, reference_no)
    return Response(result)


@api_view(["POST"])
def gem_bid_results_view(request):
    gem_ids = request.data.get("gem_ids")
    if not gem_ids or not isinstance(gem_ids, list):
        return Response({"error": "gem_ids list is required"}, status=400)
    results = extract_bid_results(gem_ids)
    return Response(results)