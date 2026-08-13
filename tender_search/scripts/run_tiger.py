import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from tender_search.services.tender_tiger import login_tiger

email = settings.TENDER_TIGER_EMAIL
password = settings.TENDER_TIGER_PASSWORD

if not email or not password:
    print("ERROR: TENDER_TIGER_EMAIL and TENDER_TIGER_PASSWORD must be set in .env")
    sys.exit(1)
referenceNo = "64265344B"
result = login_tiger(email, password, referenceNo, drive_folder_id=settings.GOOGLE_DRIVE_FOLDER_ID or None)
print(result)
