from pathlib import Path

from playwright.sync_api import sync_playwright

from .browser import detect_chrome_path
from .google_drive import upload_to_drive


import asyncio

print("Policy:", asyncio.get_event_loop_policy())

try:
    loop = asyncio.get_event_loop()
    print("Loop:", type(loop))
except Exception as e:
    print("No loop:", e)

def login_tender247(email: str, password: str, tender_id: str = "", drive_folder_id: str | None = None) -> dict:
    drive_result = None
    file_path = None
    result_data = {}
    chrome_path = detect_chrome_path()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome_path, headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        try:
            print(f"[Tender247] Navigating to homepage...")
            page.goto("https://www.tender247.com/auth/tender", timeout=50000)

            page.locator("button:has-text('Sign Up')").click()

            page.wait_for_timeout(2000)

            page.locator("input[name='emailId']").first.fill(email)
            page.locator("input[name='password']").first.fill(password)

            page.locator("button[type='submit']:has-text('Submit')").click()

            page.wait_for_timeout(5000)

            close_btn = page.locator("button:has(span.sr-only:text('Close'))")
            if close_btn.count() > 0:
                print("[Tender247] Closing dialog...")
                close_btn.click()
                page.wait_for_timeout(1000)

            if tender_id:
                print(f"[Tender247] Seeking tender ID field for '{tender_id}'...")
                tender_input = page.locator("input[placeholder='Organization Tender ID']").first

                if not tender_input.is_visible():
                    print("[Tender247] Input not visible, clicking Tender Filters heading...")
                    filters_heading = page.locator("h2:has-text('Tender Filters')")
                    if filters_heading.count() > 0:
                        filters_heading.click()
                        page.wait_for_timeout(1000)

                tender_input.wait_for(state="visible", timeout=5000)
                print(f"[Tender247] Filling tender ID: {tender_id}")
                tender_input.fill(tender_id)
                page.wait_for_timeout(500)

                print("[Tender247] Clicking SEARCH...")
                search_btn = page.get_by_role("button", name="SEARCH", exact=True)
                search_btn.wait_for(state="visible", timeout=5000)
                search_btn.click()
                page.wait_for_timeout(20000)

                print("[Tender247] Clicking view button to open tender details...")
                view_icon = page.locator("span.cursor-pointer:has(svg)").first
                view_icon.wait_for(state="visible", timeout=10000)

                with page.expect_popup() as popup_info:
                    view_icon.click()
                detail_page = popup_info.value
                detail_page.wait_for_load_state("networkidle")
                detail_page.wait_for_timeout(3000)

                print("[Tender247] Clicking Download All Documents...")
                download_btn = detail_page.locator("span:has-text('Download All Documents')")
                download_btn.wait_for(state="visible", timeout=10000)

                download_dir = Path("D:\\.temp")
                download_dir.mkdir(exist_ok=True)

                with detail_page.expect_download(timeout=30000) as download_info:
                    download_btn.first.click()
                download = download_info.value

                suggested = download.suggested_filename or f"{tender_id}.zip"
                file_path = download_dir / suggested
                download.save_as(file_path)
                print(f"[Tender247] Downloaded: {file_path}")

            success = "Sign Up" not in (page.locator("button:has-text('Sign Up')").inner_text() if page.locator("button:has-text('Sign Up')").count() > 0 else "")

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
        print(f"[Tender247] Uploading to Google Drive...")
        drive_result = upload_to_drive(str(file_path), folder_id=drive_folder_id)
        print(f"[Tender247] Uploaded: {drive_result['name']} — {drive_result['webViewLink']}")
        result_data["drive"] = drive_result

    return result_data
