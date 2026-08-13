import os, re
import sys
import json
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from tender_search.services.pdf_parser import parse_gem_pdf_service, parse_and_save_gem_pdf

pdf_paths = glob.glob(r"D:\temp\*.pdf")

def preview_db_save(gem_id: str, data: dict):
    """Preview what would be saved to DB from already-parsed data. No writes."""
    from tender_search.services.pdf_parser import _build_tech_spec_markdown
    import json

    print(f"\n--- PREVIEW OF DB SAVE ({gem_id}) ---")
    print(f"TenderMerged:")
    print(f"  totalquantity -> {data.get('Total_Quantity')}")
    print(f"  itemcategory  -> {data.get('Item_Category_String')}")
    print(f"  emd           -> {json.dumps(data.get('EMD_Details', {}), ensure_ascii=False)}")
    print(f"  parsestatus   -> COMPLETED")

    has_links = any(s.get("Type") == "Document Links" for s in data.get("Technical_Specifications", []))
    if has_links:
        print(f"\nTenderMerged.size:")
        print(f"  -> 'External Links'")
        print(f"\nTenderFiles (links saved as new rows):")
        for spec in data.get("Technical_Specifications", []):
            if spec["Type"] == "Document Links":
                item_name = spec.get("Item_Name", "Unknown")
                if spec.get("Specification_Document_Link"):
                    print(f"  + name='{item_name}: Specification Document', url='{spec['Specification_Document_Link']}'")
                if spec.get("BOQ_Document_Link"):
                    print(f"  + name='{item_name}: BOQ Document', url='{spec['BOQ_Document_Link']}'")
    else:
        print(f"\nTenderMerged.size (markdown):")
        for spec in data.get("Technical_Specifications", []):
            print(_build_tech_spec_markdown(spec))
            print()

    print(f"\nReportings (inserted as new rows, no delete):")
    for group in data.get("Consignees", []):
        for c in group.get("Consignee_Data", []):
            print(f"  + officer='{c.get('Consignee_Name','')}', address='{c.get('Address','')}', quantity='{c.get('Quantity','')}'")
if not pdf_paths:
    print("No PDF files found in D:\\temp")
    sys.exit(1)

for pdf_path in pdf_paths:
    print(f"\n{'='*60}")
    print(f"Parsing: {pdf_path}")
    print(f"{'='*60}")
    try:
        # gem_id= _filename_to_gem_id(filename=pdf_path)
        # print(gem_id)
        # data = parse_gem_pdf_service(pdf_path)
        # print(json.dumps(data, indent=2, ensure_ascii=False))
        # preview_db_save(data=data, gem_id=gem_id)
        parse_and_save_gem_pdf(pdf_path=pdf_path)
        
    except Exception as e:
        print(f"ERROR: {e}")