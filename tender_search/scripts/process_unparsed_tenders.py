import os
import re
import sys
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

import requests
from django.conf import settings
from django.db.models import Q
from tender_search.models import TenderMerged, TenderFiles
from tender_search.services.pdf_parser import parse_and_save_gem_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TEMP_DIR = settings.TENDER_PARSING_TEMP_DIR

DRIVE_FILE_ID_RE = re.compile(r"/file/d/([^/]+)/")


def _extract_drive_file_id(url: str) -> str | None:
    m = DRIVE_FILE_ID_RE.search(url)
    return m.group(1) if m else None


def _download_from_drive(file_id: str, dest_path: str) -> bool:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    session = requests.Session()

    response = session.get(url, stream=True)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        first_chunk = response.iter_content(chunk_size=32768).__next__()
        text = first_chunk.decode("utf-8", errors="replace")
        m = re.search(r'confirm=([0-9A-Za-z\-_]+)', text)
        if m:
            confirm_token = m.group(1)
            url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
            response = session.get(url, stream=True)
            response.raise_for_status()
        else:
            response = session.get(url, stream=True)
            response.raise_for_status()

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return True


def process_unparsed_tenders():
    os.makedirs(TEMP_DIR, exist_ok=True)

    tenders = TenderMerged.objects.filter(
        tendertype='GEM',
        size__isnull=True,
        tenderfiles__tags__contains=['tenderDocument'],
    ).distinct()

    total = tenders.count()
    logger.info("Found %d GEM tender(s) with empty size and tenderDocument URL", total)

    succeeded = 0
    failed = 0

    for tender in tenders:
        refno = tender.referenceno
        logger.info("Processing: %s", refno)

        tf = TenderFiles.objects.filter(
            tendermergedid=tender,
            tags__contains=['tenderDocument'],
        ).first()
        if not tf or not tf.url:
            logger.warning("  No tenderDocument URL for %s, skipping", refno)
            failed += 1
            continue

        file_id = _extract_drive_file_id(tf.url)
        if not file_id:
            logger.warning("  Could not extract Drive file ID from URL: %s", tf.url)
            failed += 1
            continue

        safe_name = refno.replace('/', '-')
        pdf_path = os.path.join(TEMP_DIR, f"{safe_name}.pdf")

        try:
            logger.info("  Downloading file_id=%s -> %s", file_id, pdf_path)
            _download_from_drive(file_id, pdf_path)
        except Exception as e:
            logger.error("  Download failed for %s: %s", refno, e)
            failed += 1
            continue

        try:
            logger.info("  Parsing and saving to DB...")
            result = parse_and_save_gem_pdf(pdf_path)
            if result.get("db_save", {}).get("success"):
                logger.info("  SUCCESS: %s", refno)
                succeeded += 1
            else:
                err = result.get("db_save", {}).get("error", "unknown error")
                logger.error("  DB save failed for %s: %s", refno, err)
                failed += 1
        except Exception as e:
            logger.error("  Parse failed for %s: %s", refno, e)
            try:
                t = TenderMerged.objects.get(referenceno=refno)
                t.parsestatus = "FAILED"
                t.parseerror = str(e)
                t.save()
            except Exception:
                pass
            failed += 1
        finally:
            if os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    logger.info("  Deleted temp file: %s", pdf_path)
                except Exception as e:
                    logger.warning("  Could not delete %s: %s", pdf_path, e)

        time.sleep(0.5)

    logger.info("=" * 50)
    logger.info("Done. Total=%d, Succeeded=%d, Failed=%d", total, succeeded, failed)


if __name__ == "__main__":
    process_unparsed_tenders()
