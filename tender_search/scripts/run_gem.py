import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from tender_search.services.gem_bid_results import extract_bid_results

results = extract_bid_results(["GEM/2026/B/7669772"])

for r in results:
    print(r)