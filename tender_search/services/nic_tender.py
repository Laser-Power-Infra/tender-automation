from playwright.sync_api import sync_playwright

from .browser import detect_chrome_path
from .ocr import ocr_captcha


def search_tender(website: str, reference_no: str) -> dict:
    chrome_path = detect_chrome_path()
    print(f"[Non-GEM] Chrome path: {chrome_path}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=chrome_path,
            headless=False,
        )
        page = browser.new_page()

        try:
            print(f"[Non-GEM] Navigating to {website}")
            page.goto(website, wait_until="networkidle", timeout=60000)

            print("[Non-GEM] Clicking Advanced Search...")
            page.locator("a[title='Advanced Search']").click()
            page.wait_for_timeout(2000)

            page.locator("#TenderType").select_option("1")
            page.locator("#tenderId").fill(reference_no)

            for attempt in range(1, 6):
                if attempt > 1:
                    print(f"[Non-GEM] Captcha retry {attempt}/5")
                    page.locator("button[name='captcha']").click()
                    page.wait_for_timeout(2000)

                captcha_img = page.locator("#captchaImage")
                if not captcha_img.is_visible():
                    continue

                src = captcha_img.get_attribute("src")
                if not src:
                    continue

                captcha_text = ocr_captcha(src.replace("data:image/png;base64,", ""))
                if not captcha_text:
                    print(f"  OCR returned empty, retrying")
                    continue

                page.locator("#captchaText").fill(captcha_text)
                page.locator("#submit").click()
                page.wait_for_timeout(3000)

                error_visible = page.locator("span.error").first.is_visible()
                if not error_visible:
                    print(f"[Non-GEM] Search submitted successfully!")
                    return {
                        "success": True,
                        "captcha_detected": captcha_text,
                        "attempts": attempt,
                        "error": None,
                    }

                print(f"  Attempt {attempt}: invalid captcha")

            return {
                "success": False,
                "captcha_detected": None,
                "attempts": 5,
                "error": "Captcha failed after 5 attempts",
            }

        except Exception as e:
            return {
                "success": False,
                "captcha_detected": None,
                "attempts": 0,
                "error": str(e),
            }
        finally:
            browser.close()
