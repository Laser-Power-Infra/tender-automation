import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from tender_search.services.gem_ra_pdf_downloader import download_ra_pdf

result = download_ra_pdf("GEM/2026/B/7828724")
# result = download_ra_pdf("GEM/2026/B/7851349")
print(result)