"""NIC_DOWNLOAD jobs from the v2 tasks queue:
  {"type": "NIC_DOWNLOAD", "referenceNo": "<Tender ID>", "portal": "https://wbtenders.gov.in", "client_id": ...}

Search `portal` for referenceNo in the same search box the keyword scrape uses, download the tender's zip
(same captcha flow), unzip and upload every file to S3. The worker sends the files as file.fetched_success
to client_id. Not found / no documents -> Requeue: back to the end of the queue.

Manual run (prints the S3 links, no webhook, no queue):
  uv run python -m automation_v2.nic_fetch <portal> <referenceNo> [<referenceNo> ...]
"""
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_v2")

from playwright.sync_api import sync_playwright  # noqa: E402

from .dispatch import Requeue  # noqa: E402
from .fetch import BOQ_FILE, _file, _non_gem_tag  # noqa: E402
from .lib.zip_utils import extract_and_upload  # noqa: E402
from tender_search.constants import TENDER_FILE_TYPES  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent / "nic_automation" / "src"))
from nic_automation.scraper import log, parse_results, tender_details  # noqa: E402


def _download(ref: str, portal: str, headless: bool) -> str | None:
    """Zip path of `ref`'s documents on `portal`, or None if not found / no zip."""
    chrome = os.environ.get("CHROME_PATH")  # the Docker image ships /usr/bin/chromium, not Playwright's build
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless,
                                    executable_path=chrome if chrome and os.path.exists(chrome) else None)
        try:
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(portal)
                page.fill("#SearchDescription", ref)
                page.press("#SearchDescription", "Enter")
                page.wait_for_load_state()
                rows = parse_results(page) if page.locator("#table").count() else []
                row = next((r for r in rows if r["id"] == ref), rows[0] if len(rows) == 1 else None)
                if not row:
                    log(f"[{ref}] not found on {portal} ({len(rows)} result rows)")
                    return None
                details = tender_details(context, row["href"], row["id"])
                if details and details["zip_path"]:
                    return details["zip_path"]
                log(f"[{ref}] found on {portal} but no documents")
            except Exception as e:  # portal down / page changed: retried later like "not found"
                log(f"[{ref}] {portal}: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")
        finally:
            browser.close()
    return None


def _tag(key: str) -> str:
    """BOQ Excel -> boqComparativeChart, else tenderDocument (same BOQ rule as the non-GeM fetcher)."""
    is_boq = _non_gem_tag(key) == BOQ_FILE
    return TENDER_FILE_TYPES["BOQ_COMPARATIVE_CHART" if is_boq else "TENDER_DOCUMENT"]


def fetch_nic(job, headless: bool | None = None) -> dict:
    from django.conf import settings

    ref, portal = job.referenceNo, job.portal
    zip_path = _download(ref, portal, settings.HEADLESS_BROWSER if headless is None else headless)
    if not zip_path:
        raise Requeue(f"{ref}: tender or its documents not found on {portal}")
    # upload after the browser is closed, like the other fetchers
    files = [_file(s3, _tag(s3["key"]), "nic") for s3 in extract_and_upload(zip_path, ref) if s3.get("url")]
    if not files:
        raise Requeue(f"{ref}: zip from {portal} had no files")
    return {"files": files, "bidStatus": None}


if __name__ == "__main__":
    from types import SimpleNamespace

    sys.stdout.reconfigure(errors="replace")  # page fields contain ₹, which crashes a cp1252 console
    if len(sys.argv) < 3:
        sys.exit("usage: python -m automation_v2.nic_fetch <portal> <referenceNo> [<referenceNo> ...]")
    for ref in sys.argv[2:]:
        try:
            result = fetch_nic(SimpleNamespace(referenceNo=ref, portal=sys.argv[1]))
        except Requeue as e:
            print(f"{ref}: NOT FETCHED (worker would requeue): {e}")
            continue
        print(f"{ref}: {len(result['files'])} file(s)")
        for f in result["files"]:
            print(f"  {f['name']}  {f['url']}")
