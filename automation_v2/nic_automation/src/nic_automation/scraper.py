import base64
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from nic_automation.captcha_decoder import fix_case, save_captcha, solve_candidates
from nic_automation.target_websites import CATEGORY_CONFIG, EXCLUSION_KEYWORDS, website


def is_excluded(text: str) -> bool:
    text = text.lower()
    return any(k.lower() in text for k in EXCLUSION_KEYWORDS)


def parse_results(page):
    """Rows of the result table: detail link and the tender id shown in the list."""
    rows = []
    for tr in page.locator("#table tr.even, #table tr.odd").all():
        link = tr.locator("a[title='View Tender Information']")
        cell = tr.locator("td").nth(4).inner_text().replace(link.inner_text(), "")
        refs = re.findall(r"\[([^\]]*)\]", cell)  # [ref no][tender id]
        rows.append({"id": refs[-1] if refs else link.get_attribute("href"),
                     "href": urljoin(page.url, link.get_attribute("href"))})
    return rows


# every "label | value" pair of the page, keyed by the page's own label; nested tables (documents) are skipped
PAGE_FIELDS_JS = """() => {
    const clean = t => t.replace(/ /g, ' ').trim();
    const out = {};
    for (const td of document.querySelectorAll('td.td_caption')) {
        const label = clean(td.innerText), val = td.nextElementSibling;
        if (!label || !val || val.querySelector('table') || val.classList.contains('td_caption') || label in out) continue;
        out[label] = clean(val.innerText);
    }
    return out;
}"""
REQUIRED = ["Tender ID", "Work Description", "EMD Amount in ₹"]


ZIP_LINK = 'a:has-text("Download as zip file")'
DOWNLOAD_DIR = Path("downloads")
CAPTCHA_TEXT = "#captchaText"
CAPTCHA_IMG = "#captchaImage"
CAPTCHA_REFRESH = "#captcha"
CAPTCHA_SUBMIT = "#Submit"
CAPTCHA_TRIES = 10
CAPTCHA_DIR = DOWNLOAD_DIR / "captcha"


def _captcha_image(tab):
    """The captcha bytes and their src (used to tell a refreshed image)."""
    src = tab.locator(CAPTCHA_IMG).get_attribute("src") or ""
    if src.startswith("data:"):
        return base64.b64decode(src.split(",", 1)[1]), src
    return tab.locator(CAPTCHA_IMG).screenshot(), src


def _refresh_captcha(tab, old_src):
    tab.click(CAPTCHA_REFRESH)
    for _ in range(20):
        tab.wait_for_timeout(250)
        if (tab.locator(CAPTCHA_IMG).get_attribute("src") or "") != old_src:
            return


def _auto_captcha(tab, tender_id, tries=CAPTCHA_TRIES):
    """Fill the DocDownCaptcha form; success returns to the details page with an sp= zip link."""
    try:
        tab.locator(CAPTCHA_IMG).wait_for(timeout=20_000)
    except PlaywrightTimeoutError:
        return False
    submitted = 0
    for _ in range(tries * 3):  # refreshes for unreadable images don't count as tries
        if submitted >= tries:
            break
        image, src = _captcha_image(tab)
        text = next((t for t in solve_candidates(image) if len(t) == 6), None)
        if text is None:
            print(f"[{tender_id}] captcha: unreadable, refreshing")
            _refresh_captcha(tab, src)
            continue
        text = str(fix_case(text, image))
        save_captcha(image, CAPTCHA_DIR / f"{tender_id}_{submitted + 1}_{re.sub(r'[^A-Za-z0-9]', '', text)}.png")
        submitted += 1
        print(f"[{tender_id}] captcha attempt {submitted}: {text}")
        tab.fill(CAPTCHA_TEXT, text)
        tab.click(CAPTCHA_SUBMIT)
        tab.wait_for_load_state()
        if tab.locator(f'{ZIP_LINK}[href*="sp="]').count():
            return True
        if not tab.locator(CAPTCHA_TEXT).count():
            return False
    return False


def download_zip(tab, tender_id):
    """Without sp= the link leads to a captcha; once solved (or already solved this session) it has sp= and downloads."""
    link = tab.locator(ZIP_LINK).first
    try:
        link.wait_for(timeout=15_000)
    except PlaywrightTimeoutError:
        print(f"WARNING [{tender_id}] no zip link on the page")
        return None
    if "sp=" not in (link.get_attribute("href") or ""):
        link.click()
        if not _auto_captcha(tab, tender_id):
            print(f"WARNING [{tender_id}] captcha not solved, zip skipped")
            return None
    link = tab.locator(f'{ZIP_LINK}[href*="sp="]').first
    with tab.expect_download() as dl:
        link.click()
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    path = DOWNLOAD_DIR / f"{tender_id}.zip"
    dl.value.save_as(path)
    return str(path)


def tender_details(context, href, tender_id):
    """Open the tender in its own tab; returns the page's label/value dict, or None if excluded."""
    tab = context.new_page()
    try:
        tab.goto(href)
        tab.wait_for_load_state()
        tab.wait_for_selector("text=Work Description")
        details = tab.evaluate(PAGE_FIELDS_JS)
        # Download links are not public on this page, so only name/size are captured.
        docs = []
        for sel, name_i, size_i, kind in (
            ("#table tr:has(td.td_field)", 1, 3, "NIT"),
            ("#workItemDocumenttable tr:has(td:nth-child(5))", 2, 4, None),
        ):
            for tr in tab.locator(sel).all():
                tds = tr.locator("td")
                if tds.count() > size_i and tds.first.inner_text().strip().isdigit():
                    docs.append({
                        "type": kind or tds.nth(1).inner_text().strip(),
                        "name": tds.nth(name_i).inner_text().strip(),
                        "size_kb": tds.nth(size_i).inner_text().strip(),
                    })
        details["Tenders Documents"] = docs
        missing = [k for k in REQUIRED if not details.get(k)]
        if missing:
            print(f"WARNING {href}: missing {missing}")
        if is_excluded(details.get("Work Description", "")):
            return None
        details["zip_path"] = download_zip(tab, details.get("Tender ID") or tender_id)
        return details
    finally:
        tab.close()


def _django_extract_and_upload():
    """automation_v2.lib's S3 helpers read django.conf.settings (lazy, no django.setup()/apps/DB needed)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from automation_v2.lib.zip_utils import extract_and_upload
    return extract_and_upload


def run(only_keyword: str | None = None) -> None:
    only_keyword = only_keyword or (sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.reconfigure(errors="replace")  # page fields contain ₹, which crashes a cp1252 console
    seen = set()
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        for category, subs in CATEGORY_CONFIG.items():
            for sub, cfg in subs.items():
                for keyword in cfg["keywords"]:
                    if only_keyword and keyword != only_keyword:
                        continue
                    page.goto(website[0])
                    page.fill("#SearchDescription", keyword)
                    page.press("#SearchDescription", "Enter")
                    page.wait_for_load_state()
                    if page.locator("#table").count() == 0:
                        input(f"[{keyword}] no result table; solve captcha in the browser if shown, then press Enter...")
                        page.wait_for_load_state()
                    if page.locator("#table").count() == 0:
                        continue
                    for row in parse_results(page):
                        if row["id"] in seen:
                            continue
                        seen.add(row["id"])
                        details = tender_details(context, row["href"], row["id"])
                        if details is None:
                            continue
                        results.append({"category": category, "sub_category": sub, "keyword": keyword,
                                        "href": row["href"], "id": row["id"], **details})
        failed = [r for r in results if not r["zip_path"]]
        # once one captcha passed the session carries sp=, so skipped zips download without a captcha now
        if failed and any(r["zip_path"] for r in results):
            print(f"retrying {len(failed)} tenders whose captcha failed...")
            for result in failed:
                details = tender_details(context, result["href"], result.get("Tender ID") or result["id"])
                if details:
                    result["zip_path"] = details["zip_path"]
        extract_and_upload = _django_extract_and_upload()
        for result in results:
            reference_no = result.get("Tender ID") or result["id"]
            result["reference_no"] = reference_no
            zip_path = result.pop("zip_path")
            result["s3_list"] = []
            if zip_path:
                try:
                    result["s3_list"] = extract_and_upload(zip_path, reference_no)
                except Exception as e:
                    print(f"[{reference_no}] extract/upload failed: {e}")
            result["s3_urls"] = [x["url"] for x in result["s3_list"]]
            result.pop("href", None)
            result.pop("id", None)
            print(result)
        browser.close()
