from pathlib import Path

from playwright.sync_api import sync_playwright
from django.conf import settings

from .browser import detect_chrome_path
from .google_drive import upload_to_drive


def login_tiger(email: str, password: str, reference_no: str, drive_folder_id=None) -> dict:
    chrome_path = detect_chrome_path()
    file_path = None
    result_data = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome_path, headless=True)
        page = browser.new_page()

        try:
            print(f"[Tiger] Navigating to login page...")
            page.goto(
                "https://www.tendertiger.com/User/Account?login",
                wait_until="networkidle",
                timeout=30000,
            )
            page.locator('input[name="Email"]').fill(email)
            page.locator('input[name="Password"]').fill(password)
            page.locator("#btnlogin").click()

            page.wait_for_timeout(5000)

            success = "dashboard" in page.url.lower()

            if success:
                detail_page = _search_by_reference(page, reference_no)
                file_path = _download_docs(detail_page, reference_no)

            result_data = {
                "success": success,
                "url": page.url,
                "title": page.title(),
            }
        except Exception as e:
            result_data = {"success": False, "error": str(e)}
        finally:
            browser.close()

    if file_path and drive_folder_id and result_data.get("success"):
        print(f"[Tiger] Uploading {file_path.name} to Google Drive...")
        drive_result = upload_to_drive(str(file_path), folder_id=drive_folder_id)
        result_data["drive_url"] = drive_result.get("webViewLink", "")
        result_data["drive"] = drive_result
        print(f"[Tiger] Uploaded: {drive_result['name']} — {result_data['drive_url']}")

    return result_data


def _search_by_reference(page, reference_no: str):
    print(f"[Tiger] Searching dashboard for reference {reference_no!r}...")

    filter_btn = page.locator("#new-filter-btn-tt")
    filter_btn.click()
    page.wait_for_timeout(1000)

    tid_input = page.locator("#txt_W_Tid")
    tid_input.wait_for(state="visible", timeout=15000)
    tid_input.fill(reference_no)

    search_btn = page.locator("#new-filter-view-tt .filter-footer button")
    search_btn.click()

    loader = page.locator("#tender-loader")
    try:
        loader.wait_for(state="hidden", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    return _open_matching_tender(page, reference_no)


def _open_matching_tender(page, reference_no: str):
    print(f"[Tiger] Opening tender {reference_no!r} in a new tab...")

    index = page.evaluate(
        """(referenceNo) => {
            const items = document.querySelectorAll('#myScroll li.tender-listing');
            for (let i = 0; i < items.length; i++) {
                const input = items[i].querySelector('input.form-check-input[data-tenderdata]');
                if (!input) continue;
                try {
                    const data = JSON.parse(input.dataset.tenderdata);
                    if ((data.tenderrefno || '').toLowerCase() === referenceNo.toLowerCase()) {
                        return i;
                    }
                } catch (e) {}
            }
            return -1;
        }""",
        reference_no,
    )

    if index == -1:
        print(f"[Tiger] No exact reference match found; using first result.")
        index = 0

    links = page.locator("#myScroll li.tender-listing a[href*='TenderDetail']")
    if links.count() == 0:
        raise RuntimeError("No tender detail link found in search results.")

    link = links.nth(index)
    with page.context.expect_page(timeout=30000) as new_page_info:
        link.click()
    new_page = new_page_info.value
    new_page.wait_for_load_state("networkidle", timeout=30000)
    new_page.wait_for_timeout(3000)
    return new_page


def _download_docs(detail_page, reference_no: str) -> Path:
    print(f"[Tiger] Downloading all documents for {reference_no!r}...")

    link = detail_page.locator(".all-doc-dow a[href*='GetTenderDocs']")
    link.wait_for(state="visible", timeout=30000)

    download_dir = Path(settings.TENDER_PARSING_TEMP_DIR)
    download_dir.mkdir(parents=True, exist_ok=True)
    file_path = download_dir / f"{reference_no}.zip"

    with detail_page.expect_download(timeout=60000) as download_info:
        link.click()
    download = download_info.value
    download.save_as(str(file_path))
    print(f"[Tiger] Downloaded: {file_path}")
    return file_path
