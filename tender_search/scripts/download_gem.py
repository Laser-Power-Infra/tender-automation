import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from tender_search.services.gem_pdf_downloader import download_gem_pdf

gem_id = "GEM/2026/B/7669772" # work for bid RA
# gem_id = "GEM/2026/B/7756075" # work for ongoing

result = download_gem_pdf(gem_id)

print(result)