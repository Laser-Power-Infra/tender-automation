import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from tender_search.services.non_gem_tender_pdf_downloader import login_tender247

email = settings.TENDER247_EMAIL
password = settings.TENDER247_PASSWORD
tender_id = "2026_SETCL_1029985_1"

if not email or not password:
    print("ERROR: TENDER247_EMAIL and TENDER247_PASSWORD must be set in .env")
    sys.exit(1)

result = login_tender247(email, password, tender_id, drive_folder_id=settings.GOOGLE_DRIVE_FOLDER_ID or None)
print(result)
