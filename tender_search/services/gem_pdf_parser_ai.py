import os
import json
import base64
from openai import OpenAI
from tender_search.models import TenderMerged, Reportings, TenderFiles
import time
from django.utils import timezone


def pdf_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:application/pdf;base64,{encoded}"


# def extract_pdf_data(pdf_path: str, gem_id: str) -> dict:
#     """Call OpenAI to extract data from PDF. Returns {success, data}. No DB writes."""
#     try:
#         pdf_data_url = pdf_to_base64(pdf_path)
#         client = OpenAI()

#         prompt = (
#             "Extract the following from this tender PDF:\n"
#             "1. Item Category — what category of items is being procured\n"
#             "2. Total Quantity — the total quantity across all line items\n"
#             "3. Consignees / Reporting Officers — list each officer name, their address, and the quantity allocated to them\n"
#             "4. For each Item category - detailed breakdown of technical specifications including specification, specification name, bid requirement.\n"
#             "Return ALL consignees found."
#         )

#         for attempt in range(1, 4):
#             try:
#                 response = client.chat.completions.create(
#                     model="gpt-4o-mini",
#                     messages=[{
#                         "role": "user",
#                         "content": [
#                             {"type": "text", "text": prompt},
#                             {"type": "image_url", "image_url": {"url": pdf_data_url}},
#                         ],
#                     }],
#                     response_format={
#                         "type": "json_schema",
#                         "json_schema": {
#                             "name": "tender_extraction",
#                             "strict": True,
#                             "schema": {
#                                 "type": "object",
#                                 "properties": {
#                                     "itemCategory": {"type": "string"},
#                                     "totalQuantity": {"type": "string"},
#                                     "reportings": {
#                                         "type": "array",
#                                         "items": {
#                                             "type": "object",
#                                             "properties": {
#                                                 "officer": {"type": "string"},
#                                                 "address": {"type": "string"},
#                                                 "quantity": {"type": "string"},
#                                             },
#                                             "required": ["officer", "address", "quantity"],
#                                         },
#                                     },
#                                     "size": {
#                                         "type": "array",
#                                         "items": {
#                                             "type": "object",
#                                             "properties": {
#                                                 "itemCategory": {"type": "string"},
#                                                 "TechnicalSpecifications": {"type": "string"},
#                                             },
#                                             "required": ["itemCategory", "TechnicalSpecifications"],
#                                         },
#                                     },
#                                 },
#                                 "required": ["itemCategory", "totalQuantity", "reportings", "size"],
#                             },
#                         },
#                     },
#                 )
#                 output = json.loads(response.choices[0].message.content)
#                 break
#             except Exception as e:
#                 if hasattr(e, 'status_code') and e.status_code == 429 and attempt < 3:
#                     import time
#                     time.sleep(60)
#                     continue
#                 raise

#         print(f"\n  [AI] RAW OUTPUT FOR {gem_id}:")
#         print(json.dumps(output, indent=2))
#         print("  [AI] END RAW OUTPUT\n")

#         return {"success": True, "data": output}

#     except Exception as e:
#         print(f"  [AI] FAILED for {gem_id}: {e}")
#         return {"success": False, "error": str(e)}


def extract_pdf_data(pdf_path: str, gem_id: str) -> dict:
    try:
        client = OpenAI()

        # Upload PDF to OpenAI
        with open(pdf_path, "rb") as f:
            file_obj = client.files.create(file=f, purpose="user_data")
        print(f"  [AI] Uploaded PDF to OpenAI: file_id={file_obj.id}")

        prompt = (
            "Extract the following from this tender PDF:\n"
            "1. Item Category — what category of items is being procured\n"
            "2. Total Quantity — the total quantity across all line items\n"
            "3. Consignees / Reporting Officers — list each officer name, their address, and the quantity allocated to them\n"
            "4. For each Item category - detailed breakdown of technical specifications including specification, specification name, bid requirement.\n"
            "Return ALL consignees found."
        )

        for attempt in range(1, 4):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "file", "file": {"file_id": file_obj.id}},
                        ],
                    }],
                    response_format={
                                           "type": "json_schema",
                                           "json_schema": {
                                               "name": "tender_extraction",
                                               "strict": True,
                                               "schema": {
                                                   "type": "object",
                                                   "properties": {
                                                       "itemCategory": {"type": "string"},
                                                       "totalQuantity": {"type": "string"},
                                                       "reportings": {
                                                           "type": "array",
                                                           "items": {
                                                               "type": "object",
                                                               "properties": {
                                                                   "officer": {"type": "string"},
                                                                   "address": {"type": "string"},
                                                                   "quantity": {"type": "string"},
                                                               },
                                                               "required": ["officer", "address", "quantity"],
                                                           },
                                                       },
                                                       "size": {
                                                           "type": "array",
                                                           "items": {
                                                               "type": "object",
                                                               "properties": {
                                                                   "itemCategory": {"type": "string"},
                                                                   "TechnicalSpecifications": {"type": "string"},
                                                               },
                                                               "required": ["itemCategory", "TechnicalSpecifications"],
                                                           },
                                                       },
                                                   },
                                                   "required": ["itemCategory", "totalQuantity", "reportings", "size"],
                                               },
                                           },
                                       },
                                   )
                output = json.loads(response.choices[0].message.content)
                break
            except Exception as e:
                if hasattr(e, 'status_code') and e.status_code == 429 and attempt < 3:
                    time.sleep(60)
                    continue
                raise

        # Delete file from OpenAI
        client.files.delete(file_obj.id)

        print(f"\n  [AI] RAW OUTPUT FOR {gem_id}:")
        print(json.dumps(output, indent=2))
        print("  [AI] END RAW OUTPUT\n")

        return {"success": True, "data": output}

    except Exception as e:
        print(f"  [AI] FAILED for {gem_id}: {e}")
        return {"success": False, "error": str(e)}

def save_extraction_to_db(
    referenceno: str,
    file_tag: str,
    file_url: str,
    pdf_path: str = "",
    item_category: str = "",
    total_quantity: str = "",
    size: str = None,
    reportings: list = None,
) -> dict:
    """Save extraction results to TenderMerged, TenderFiles, Reportings. No OpenAI calls."""
    try:
        tender = TenderMerged.objects.get(referenceno=referenceno)
    except TenderMerged.DoesNotExist:
        print(f"  [DB] TenderMerged not found for {referenceno}")
        return {"success": False, "error": f"TenderMerged not found for {referenceno}"}

    try:
        # Update TenderMerged
        # tender.itemcategory = item_category
        # tender.totalquantity = total_quantity
        # tender.size = size
        # tender.parsestatus = "COMPLETED"
        # tender.parseerror = None
        # if file_url:
        #     tender.tenderfileurl = file_url
        # tender.save()

        # Create TenderFiles entry
        if file_url:
            TenderFiles.objects.create(
                tendermergedid=tender,
                name=os.path.basename(pdf_path),
                extension="pdf",
                url=file_url,
                tags=[file_tag],
                createdat=timezone.now(),
                updatedat=timezone.now(),

            )

        # Replace Reportings rows
        # if reportings:
        #     # tender.reportings_set.all().delete()
        #     for r in reportings:
        #         Reportings.objects.create(
        #             tendermergedid=tender,
        #             officer=r.get("officer", ""),
        #             address=r.get("address", ""),
        #             quantity=r.get("quantity", ""),
        #         )

        print(f"  [DB] Saved extraction for {referenceno}")
        return {"success": True}

    except Exception as e:
        tender.parsestatus = "FAILED"
        tender.parseerror = str(e)
        tender.save()
        print(f"  [DB] FAILED for {referenceno}: {e}")
        return {"success": False, "error": str(e)}