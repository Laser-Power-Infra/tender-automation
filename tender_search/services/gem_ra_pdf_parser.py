import os
import re
import tempfile
import logging
from datetime import datetime

import pdfplumber
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DRIVE_FILE_ID_RE = re.compile(r"/file/d/([^/]+)/")


def extract_drive_file_id(url: str) -> str | None:
    m = DRIVE_FILE_ID_RE.search(url)
    return m.group(1) if m else None

def _save_to_db(gemid: str, result: dict):
    try:
        from tender_search.models import TenderMerged
        gem = TenderMerged.objects.filter(referenceno=gemid).first()

        if not gem:
            logger.error("No TenderMerged found for referenceno: %s", gemid)
            return

        start_date = result.get("start_date")
        end_date = result.get("end_date")

        if start_date:
            gem.reverseauctionstartdate = datetime.strptime(start_date, "%d-%m-%Y %H:%M:%S")
        if end_date:
            gem.reverseauctionenddate = datetime.strptime(end_date, "%d-%m-%Y %H:%M:%S")

        if start_date and end_date:
            gem.reverseauctionautomationstatus = "SUCCESS"
        else:
            gem.reverseauctionautomationstatus = None

        gem.save()
        logger.info("Saved RA dates for %s: start=%s end=%s", gemid, start_date, end_date)

    except Exception as e:
        logger.error("Error saving RA dates to DB for %s: %s", gemid, e)

def download_from_drive(file_id: str, dest_path: str) -> str:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    session = requests.Session()

    response = session.get(url, stream=True)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        first_chunk = response.iter_content(chunk_size=32768).__next__()
        text = first_chunk.decode("utf-8", errors="replace")
        m = re.search(r"confirm=([0-9A-Za-z\-_]+)", text)
        if m:
            confirm_token = m.group(1)
            url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
            response = session.get(url, stream=True)
            response.raise_for_status()

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return dest_path


def parse_ra_document(pdf_path: str) -> dict:
    start_date = None
    end_date = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            if start_date is None:
                m = re.search(r"RA\s+Start\s+Date/Time\s*[:]?\s*([\d-]+\s+[\d:]+)", text)
                if m:
                    start_date = m.group(1).strip()

            if end_date is None:
                m = re.search(r"RA\s+End\s+Date/Time\s*[:]?\s*([\d-]+\s+[\d:]+)", text)
                if m:
                    end_date = m.group(1).strip()

            if start_date is not None and end_date is not None:
                break

    return {"start_date": start_date, "end_date": end_date}


def process_ra_document(reference_no: str, drive_link: str) -> dict:
    result = {
        "reference_no": reference_no,
        "success": False,
        "start_date": None,
        "end_date": None,
        "error": None,
    }

    file_id = extract_drive_file_id(drive_link)
    if not file_id:
        result["error"] = f"Could not extract file ID from Drive link: {drive_link}"
        return result

    temp_dir = getattr(settings, "TENDER_PARSING_TEMP_DIR", tempfile.gettempdir())
    safe_name = reference_no.replace("/", "-").replace("\\", "-")
    pdf_path = os.path.join(temp_dir, f"{safe_name}_ra.pdf")

    try:
        logger.info("Downloading file_id=%s -> %s", file_id, pdf_path)
        download_from_drive(file_id, pdf_path)

        logger.info("Parsing RA document for %s...", reference_no)
        parsed = parse_ra_document(pdf_path)
        result["start_date"] = parsed["start_date"]
        result["end_date"] = parsed["end_date"]

        if result["start_date"] is None and result["end_date"] is None:
            result["error"] = "Could not find Start/End Date in RA document"
        else:
            result["success"] = True
            logger.info("Parsed RA document for %s: start=%s end=%s", reference_no, result["start_date"], result["end_date"])

    except Exception as e:
        logger.exception("RA document processing failed")
        result["error"] = str(e)

    finally:
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
                logger.info("Deleted temp file: %s", pdf_path)
            except Exception as e:
                logger.warning("Could not delete %s: %s", pdf_path, e)

    _save_to_db(reference_no, result)
    return result