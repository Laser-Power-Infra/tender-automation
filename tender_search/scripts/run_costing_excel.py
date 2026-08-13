import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from tender_search.services.costing_excel_parse import parse_costing_excel

# link = "https://www.appsheet.com/Template/gettablefileurl?APPNAME=LASERTENDINGCOSTINGATT-3832607&TABLENAME=%0ATENDER%20COSTING%20ATTACHMENT&FILENAME=TENDER%20COSTING%20ATTACHMENT_Files_%2FTM26Y-00136.TOTAL%20COST%20ATTACHMENT.071303.xlsx"
# link ="https://www.appsheet.com/Template/gettablefileurl?APPNAME=LASERTENDINGCOSTINGATT-3832607&TABLENAME=%0ATENDER%20COSTING%20ATTACHMENT&FILENAME=TENDER%20COSTING%20ATTACHMENT_Files_%2FTM24Y-00360.TOTAL%20COST%20ATTACHMENT.124046.xlsx"
link ="Z:\\COSTING & INVOLVEMENT\\2025-26\\01_JANUARY 2026\\GEM-16-01-2026-18185-PGCIL\\costing_18185.xlsx"
result = parse_costing_excel(gemid="GEM/2026/B/7079293", appsheet_link=link)
print(result)
