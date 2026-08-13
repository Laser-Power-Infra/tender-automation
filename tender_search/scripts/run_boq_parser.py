import os
import sys
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from tender_search.services.boq_parser import process_boq


referenceNo="2026_NDMC_295201_1"
drive_link="https://drive.google.com/file/d/1xpeRE3zqeilI1MRMeLZfesFXxJ3tqZD4/view"
# referenceNo="2026_UAD_521241_1"
# drive_link="https://drive.google.com/file/d/19Dj4izka2oY2OhZdr6YiuROL_DtuDUNk/view?usp=drivesdk"

result = process_boq(reference_no=referenceNo, drive_link=drive_link)
# print(result)
# res=result.get("items")
 
# for i in res:
#     print(i)