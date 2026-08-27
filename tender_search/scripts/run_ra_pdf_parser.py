import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from tender_search.services.gem_ra_pdf_parser import process_ra_document

reference_no = "GEM/2026/R/718711"
# drive_link = "https://drive.google.com/file/d/1YV-iL5c4dROQIH5JMs6OrVPhFQdndN67/view?usp=drivesdk"
drive_link = "https://drive.google.com/file/d/16u0RDtwOeMDlTuNSN1XXVgUqSuPapi_M/view?usp=drivesdk"


result = process_ra_document(reference_no=reference_no, drive_link=drive_link)
print(result)