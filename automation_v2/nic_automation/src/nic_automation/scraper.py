import base64
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from nic_automation.captcha_decoder import _model, fix_case, solve_candidates
from nic_automation.target_websites import CATEGORY_CONFIG, EXCLUSION_KEYWORDS, website


# per thread: "[wbtenders.gov.in] [EPC/Distribution 12/40 'PSS']", set per keyword so every line says where it is
_local = threading.local()


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {getattr(_local, 'ctx', '')} {msg}".replace("  ", " "), flush=True)


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
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
CAPTCHA_TEXT = "#captchaText"
CAPTCHA_IMG = "#captchaImage"
CAPTCHA_REFRESH = "#captcha"
CAPTCHA_SUBMIT = "#Submit"
CAPTCHA_TRIES = 10


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
            log(f"[{tender_id}] captcha: unreadable, refreshing")
            _refresh_captcha(tab, src)
            continue
        text = str(fix_case(text, image))
        submitted += 1
        log(f"[{tender_id}] captcha attempt {submitted}/{tries}: {text}")
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
        log(f"WARNING [{tender_id}] no zip link on the page")
        return None
    if "sp=" not in (link.get_attribute("href") or ""):
        link.click()
        if not _auto_captcha(tab, tender_id):
            log(f"WARNING [{tender_id}] captcha not solved, sent without documents")
            return None
    link = tab.locator(f'{ZIP_LINK}[href*="sp="]').first
    with tab.expect_download() as dl:
        link.click()
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    path = DOWNLOAD_DIR / f"{tender_id}.zip"
    dl.value.save_as(path)
    log(f"[{tender_id}] zip downloaded")
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
            log(f"WARNING [{tender_id}] page missing {missing}")
        if is_excluded(details.get("Work Description", "")):
            log(f"[{tender_id}] excluded (Work Description matches exclusion list)")
            return None
        details["zip_path"] = download_zip(tab, details.get("Tender ID") or tender_id)
        return details
    finally:
        tab.close()


def _use_v2_lib():
    """automation_v2.lib helpers read django.conf.settings (lazy, no django.setup()/apps/DB needed)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _finish(tender, extract_and_upload) -> None:
    """Upload the tender's zip to S3; keep only the documents that came from it, each with its url."""
    reference_no = tender.get("Tender ID") or tender["id"]
    tender["reference_no"] = reference_no
    zip_path = tender.pop("zip_path")
    s3_list = []
    if zip_path:
        log(f"[{reference_no}] uploading zip")
        try:
            s3_list = extract_and_upload(zip_path, reference_no)
        except Exception as e:
            log(f"ERROR [{reference_no}] extract/upload failed: {e}")
    urls = {x["key"].rsplit("/", 1)[-1]: x["url"] for x in s3_list}  # file name -> link
    for doc in tender["Tenders Documents"]:
        doc["url"] = urls.get(doc["name"])
    # only documents that came from the zip and are on S3; the rest (e.g. the NIT) are dropped
    tender["Tenders Documents"] = [d for d in tender["Tenders Documents"] if d["url"]]
    tender.pop("href", None)
    tender.pop("id", None)


def _scrape_group(portal, group, seen, seen_lock, headless, extract_and_upload, finish) -> None:
    """One sub-category's keywords on one portal, in this thread's own browser (Playwright objects are per thread).
    Fills each item of `group` in place; a browser crash marks the unfinished items failed instead of raising."""
    host = urlparse(portal).netloc
    label = f"{group[0]['category']}/{group[0]['sub_category']}"
    _local.ctx = f"[{host}] [{label}]"
    done = 0
    try:
        chrome = os.environ.get("CHROME_PATH")  # the Docker image ships /usr/bin/chromium, not Playwright's build
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless,
                                        executable_path=chrome if chrome and os.path.exists(chrome) else None)
            context = browser.new_context()
            page = context.new_page()
            try:  # one check per group, so a dead portal doesn't cost a timeout per keyword
                page.goto(portal)
                page.wait_for_selector("#SearchDescription", timeout=30_000)
            except Exception as e:
                log(f"ERROR portal skipped: {type(e).__name__}: {str(e).splitlines()[0]}")
                for item in group:
                    item["error"] = f"portal unreachable / not a NIC search page: {type(e).__name__}"
                    finish(item)
                done = len(group)
                return
            any_zip = False  # once one captcha passed, the session carries sp= and later zips download without a captcha
            for ki, item in enumerate(group, 1):
                keyword = item["keyword"]
                _local.ctx = f"[{host}] [{label} {ki}/{len(group)} '{keyword}']"
                try:
                    log("searching...")
                    page.goto(portal)
                    page.fill("#SearchDescription", keyword)
                    page.press("#SearchDescription", "Enter")
                    page.wait_for_load_state()
                    if page.locator("#table").count() == 0:
                        if page.get_by_text("No Tenders found").count():
                            log("done: 0 tenders (No Tenders found)")
                        else:
                            item["error"] = "no result table and no 'No Tenders found' message (search captcha?)"
                            log(f"ERROR {item['error']}")
                        finish(item)
                        done = ki
                        continue
                    rows = parse_results(page)
                    with seen_lock:  # shared across sub-categories: a tender found twice is opened once
                        new = [r for r in rows if r["id"] not in seen]
                        seen.update(r["id"] for r in new)
                    log(f"{len(rows)} result rows ({len(new)} new, {len(rows) - len(new)} already seen)")
                    for ti, row in enumerate(new, 1):
                        log(f"tender {ti}/{len(new)} {row['id']}: opening")
                        details = tender_details(context, row["href"], row["id"])
                        if details is None:
                            continue
                        any_zip = any_zip or bool(details["zip_path"])
                        item["tenders"].append({"category": item["category"], "sub_category": item["sub_category"],
                                                "keyword": keyword, "href": row["href"], "id": row["id"], **details})
                except Exception as e:  # keep tenders already collected; move on to the next keyword
                    item["error"] = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
                    log(f"ERROR {item['error']} ({len(item['tenders'])} tenders kept)")
                failed = [t for t in item["tenders"] if not t["zip_path"]]
                if failed and any_zip:
                    log(f"retrying {len(failed)} tenders whose captcha failed")
                    for tender in failed:
                        try:
                            details = tender_details(context, tender["href"], tender.get("Tender ID") or tender["id"])
                            if details:
                                tender["zip_path"] = details["zip_path"]
                        except Exception as e:
                            log(f"WARNING [{tender['id']}] retry failed: {e}")
                        log(f"[{tender['id']}] {'retry ok' if tender['zip_path'] else 'still no zip'}")
                for tender in item["tenders"]:
                    _finish(tender, extract_and_upload)
                if not item["error"]:
                    log(f"done: {len(item['tenders'])} tenders")
                finish(item)
                done = ki
            browser.close()
    except Exception as e:  # browser crash: the other sub-categories keep going
        err = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
        log(f"ERROR browser crashed, {len(group) - done} keyword(s) not searched: {err}")
        for item in group[done:]:
            item["error"] = item["error"] or f"browser crashed: {err}"
            finish(item)
    finally:
        _local.ctx = ""


def scrape(portals: list[str], only_keyword: str | None = None, headless: bool = False,
           on_keyword=None) -> list[dict]:
    """One item per (portal, keyword) searched: {portal, category, sub_category, keyword, tenders, error}.
    Per portal, every sub-category runs at the same time in its own browser; portals run one after another.
    `on_keyword(item)` is called (from a worker thread) as soon as each keyword is finished (uploads done).
    A tender whose document captcha failed is still in `tenders`; its "Tenders Documents" is just empty
    (that list only holds files from the downloaded zip, each with its S3 url)."""
    _use_v2_lib()
    from automation_v2.lib.zip_utils import extract_and_upload
    _model()  # load the OCR model once here, not racing in every thread
    seen, seen_lock = set(), threading.Lock()
    items = []
    keywords = [(category, sub, keyword) for category, subs in CATEGORY_CONFIG.items()
                for sub, cfg in subs.items() for keyword in cfg["keywords"]
                if not only_keyword or keyword.lower() == only_keyword.lower()]
    started = time.monotonic()
    log(f"scrape: {len(portals)} portal(s) x {len(keywords)} keyword(s)")

    def finish(item) -> None:
        if on_keyword:
            on_keyword(item)

    for pi, portal in enumerate(portals, 1):
        portal_items = [{"portal": portal, "category": c, "sub_category": s, "keyword": k,
                         "tenders": [], "error": None} for c, s, k in keywords]
        items += portal_items
        groups = {}
        for item in portal_items:
            groups.setdefault((item["category"], item["sub_category"]), []).append(item)
        log(f"portal {pi}/{len(portals)} {portal}: {len(groups)} sub-categories in parallel")
        with ThreadPoolExecutor(max_workers=max(len(groups), 1)) as pool:
            futures = [pool.submit(_scrape_group, portal, g, seen, seen_lock, headless, extract_and_upload, finish)
                       for g in groups.values()]
            for f in futures:
                f.result()
    results = [t for i in items for t in i["tenders"]]
    bad = sum(1 for i in items if i["error"])
    with_docs = sum(1 for r in results if r["Tenders Documents"])
    log(f"scrape done in {(time.monotonic() - started) / 60:.1f}m: {len(items)} keyword searches "
        f"({len(items) - bad} ok, {bad} failed), {len(results)} tenders ({with_docs} with documents)")
    return items


def run(only_keyword: str | None = None) -> None:
    """Manual run: `python -m nic_automation [keyword]` prints each keyword's array as soon as it's done."""
    only_keyword = only_keyword or (sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.reconfigure(errors="replace")  # page fields contain ₹, which crashes a cp1252 console

    def show(item):
        if item["tenders"]:
            print(json.dumps(item["tenders"], ensure_ascii=False, indent=2), flush=True)

    scrape(website, only_keyword, on_keyword=show)
