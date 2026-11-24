import base64
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from nic_automation.captcha_decoder import _model, fix_case, solve_candidates
from nic_automation.target_websites import CATEGORY_CONFIG, EXCLUSION_KEYWORDS, website


# per thread: ctx = the website being scraped ("wbtenders.gov.in"), problems = {tender id: why it has no files}
_local = threading.local()
_progress_lock = threading.Lock()
_progress_at = {}   # website -> time of its last progress line
ORGS_SEARCHED = {}  # portal -> organisations walked by org_scraper, for the summary


def log(msg: str) -> None:
    """`date time  website  msg` in one write, so parallel browsers cannot mix up a multi-line block."""
    parts = (f"{datetime.now():%Y-%m-%d %H:%M:%S}", getattr(_local, "ctx", ""), msg)
    sys.stdout.write("  ".join(p for p in parts if p) + "\n")
    sys.stdout.flush()


def _problem(tender_id: str, why: str) -> None:
    """Remember why a tender has no files; log_block shows it next to the tender instead of a separate line."""
    if not hasattr(_local, "problems"):
        _local.problems = {}
    _local.problems[tender_id] = why


def why_no_files(tender_id: str) -> str | None:
    return getattr(_local, "problems", {}).pop(tender_id, None)


def progress(text: str, every: int = 300) -> None:
    """At most one line per website every `every` seconds: shows the job is alive while nothing is found."""
    host, now = getattr(_local, "ctx", ""), time.monotonic()
    with _progress_lock:
        if now - _progress_at.setdefault(host, now) < every:
            return
        _progress_at[host] = now
    log(f"progress: {text}")


def log_block(where: str, tenders: list[dict]) -> None:
    """One block per keyword / organisation that found tenders: each tender with its files and links."""
    lines = [where, f"    {len(tenders)} tender{'' if len(tenders) == 1 else 's'} found"]
    for t in tenders:
        ref, docs = t["reference_no"], t["Tenders Documents"]
        why = why_no_files(ref) or "no listed document was in the zip"
        lines.append(f"    {ref}   {len(docs)} file{'' if len(docs) == 1 else 's'}" if docs
                     else f"    {ref}   NO FILES ({why})")
        width = max((len(d["name"]) for d in docs), default=0)
        lines += [f"        {d['name']:<{width}}   {d['url']}" for d in docs]
    log("\n".join(lines) + "\n")


def log_summary(portal: str, keyword_items: list[dict], org_items: list[dict], window: str, minutes: float,
                crashed: list[str] = ()) -> None:
    """Per website: tenders found per category, one UNTITLED row for the organisation flow, then every error."""
    def counts(items):
        tenders = [t for i in items for t in i["tenders"]]
        return len(tenders), sum(1 for t in tenders if t["Tenders Documents"])

    by_cat = {}
    for it in keyword_items:
        by_cat.setdefault(it["category"], []).append(it)
    rows = [(cat, f"{len(its)} kw", *counts(its)) for cat, its in by_cat.items()]
    orgs = ORGS_SEARCHED.get(portal)
    rows.append(("UNTITLED", "-" if orgs is None else f"{orgs} orgs", *counts(org_items)))
    rows.append(("TOTAL", "", sum(r[2] for r in rows), sum(r[3] for r in rows)))
    errors = [f"{i['category']} > {i['keyword']}: {i['error']}" for i in keyword_items if i["error"]]
    errors += [f"UNTITLED > {i['organisation'] or 'website'}: {i['error']}" for i in org_items if i["error"]]
    errors += list(crashed)
    w = max(len(r[0]) for r in rows) + 3
    lines = [f"SUMMARY  {window}  ({minutes:.1f} min)",
             f"    {'Category':<{w}}{'Searched':<10}{'Tenders':>8}{'With files':>13}"]
    lines += [f"    {c:<{w}}{s:<10}{t:>8}{f:>13}" for c, s, t, f in rows]
    if errors:
        lines += [f"    Errors: {len(errors)}"] + [f"        {e}" for e in errors]
    _local.ctx = urlparse(portal).netloc
    try:
        log("\n".join(lines) + "\n")
    finally:
        _local.ctx = ""


def is_excluded(text: str) -> bool:
    text = text.lower()
    return any(k.lower() in text for k in EXCLUSION_KEYWORDS)


IST = timezone(timedelta(hours=5, minutes=30))  # portal dates are India time; the container clock is UTC


def today_ist() -> date:
    return datetime.now(IST).date()


def published_window(days: int = 0, today: date | None = None) -> set[date]:
    """Today (IST) and the `days` days before it: the e-Published dates a run keeps."""
    today = today or today_ist()
    return {today - timedelta(days=d) for d in range(days + 1)}


def window_label(dates: set[date]) -> str:
    lo, hi = min(dates), max(dates)
    return f"{hi:%d-%b-%Y}" if lo == hi else f"{lo:%d-%b-%Y} .. {hi:%d-%b-%Y}"


def published_date(text: str) -> date | None:
    """Date part of an e-Published Date cell like "10-Nov-2026 02:15 PM"; None if it can't be read."""
    try:
        return datetime.strptime((text or "").split()[0], "%d-%b-%Y").date()
    except (ValueError, IndexError):
        return None


def published_col(page) -> int:
    """Index of the "e-Published Date" column, from the list header (S.No, e-Published Date, ... is the norm)."""
    headers = page.locator("#table tr.list_header td").all_inner_texts()
    return next((i for i, h in enumerate(headers) if "published" in h.lower()), 1)


def parse_results(page):
    """Rows of the result table: detail link, the tender id shown in the list and its e-Published date."""
    rows = []
    col = published_col(page)
    for tr in page.locator("#table tr.even, #table tr.odd").all():
        link = tr.locator("a[title='View Tender Information']")
        tds = tr.locator("td")
        cell = tds.nth(4).inner_text().replace(link.inner_text(), "")
        refs = re.findall(r"\[([^\]]*)\]", cell)  # [ref no][tender id]
        rows.append({"id": refs[-1] if refs else link.get_attribute("href"),
                     "href": urljoin(page.url, link.get_attribute("href")),
                     "published": published_date(tds.nth(col).inner_text()) if tds.count() > col else None})
    return rows


assert published_date("10-Nov-2026 02:15 PM") == date(2026, 11, 10)
assert published_date(" 06-Nov-2026 05:15 PM ") == date(2026, 11, 6)
assert published_date("") is None and published_date("NA") is None
assert published_window(2, date(2026, 11, 12)) == {date(2026, 11, 12), date(2026, 11, 11), date(2026, 11, 10)}
assert published_window(0, date(2026, 11, 12)) == {date(2026, 11, 12)}
assert window_label(published_window(2, date(2026, 11, 12))) == "10-Nov-2026 .. 12-Nov-2026"


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


# wbtenders lists all of an org's tenders on one page (723 rows seen); this only matters if a portal pages them
NEXT_PAGE = 'a#linkFwd, a:text-is("Next >")'
MAX_PAGES = 1000  # guard against a pager that never ends
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
            _refresh_captcha(tab, src)
            continue
        text = str(fix_case(text, image))
        submitted += 1
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
        _problem(tender_id, "no zip link on the page")
        return None
    if "sp=" not in (link.get_attribute("href") or ""):
        link.click()
        if not _auto_captcha(tab, tender_id):
            _problem(tender_id, "captcha not solved")
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
            log(f"WARNING {tender_id}: page missing {missing}")
        if is_excluded(details.get("Work Description", "")):
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
        try:
            s3_list = extract_and_upload(zip_path, reference_no)
        except Exception as e:
            _problem(reference_no, f"upload failed: {e}")
    urls = {x["key"].rsplit("/", 1)[-1]: x["url"] for x in s3_list}  # file name -> link
    for doc in tender["Tenders Documents"]:
        doc["url"] = urls.get(doc["name"])
    # only documents that came from the zip and are on S3; the rest (e.g. the NIT) are dropped
    tender["Tenders Documents"] = [d for d in tender["Tenders Documents"] if d["url"]]
    tender.pop("href", None)
    tender.pop("id", None)


def _scrape_group(portal, group, seen, seen_lock, headless, extract_and_upload, finish, dates) -> None:
    """One sub-category's keywords on one portal, in this thread's own browser (Playwright objects are per thread).
    Fills each item of `group` in place; a browser crash marks the unfinished items failed instead of raising."""
    host = urlparse(portal).netloc
    label = f"{group[0]['category']}/{group[0]['sub_category']}"
    _local.ctx = host
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
                log(f"ERROR {label}: portal skipped: {type(e).__name__}: {str(e).splitlines()[0]}")
                for item in group:
                    item["error"] = f"portal unreachable / not a NIC search page: {type(e).__name__}"
                    finish(item)
                done = len(group)
                return
            any_zip = False  # once one captcha passed, the session carries sp= and later zips download without a captcha
            for ki, item in enumerate(group, 1):
                keyword = item["keyword"]
                where = f"{item['category']} > {keyword}"
                try:
                    page.goto(portal)
                    page.fill("#SearchDescription", keyword)
                    page.press("#SearchDescription", "Enter")
                    page.wait_for_load_state()
                    if page.locator("#table").count() == 0:
                        if not page.get_by_text("No Tenders found").count():
                            item["error"] = "no result table and no 'No Tenders found' message (search captcha?)"
                            log(f"ERROR {where}: {item['error']}")
                        finish(item)
                        done = ki
                        continue
                    rows, pages = parse_results(page), 1
                    while pages < MAX_PAGES and page.locator(NEXT_PAGE).count():  # same paging as the organisation flow
                        page.locator(NEXT_PAGE).first.click()
                        page.wait_for_load_state()
                        known = {r["id"] for r in rows}
                        more = [r for r in parse_results(page) if r["id"] not in known]
                        if not more:  # a pager that still shows Next on its last page
                            break
                        rows += more
                        pages += 1
                    fresh = [r for r in rows if r["published"] in dates]  # only tenders e-Published in the window
                    with seen_lock:  # shared across sub-categories: a tender found twice is opened once
                        new = [r for r in fresh if r["id"] not in seen]
                        seen.update(r["id"] for r in new)
                    for row in new:
                        details = tender_details(context, row["href"], row["id"])
                        if details is None:
                            continue
                        any_zip = any_zip or bool(details["zip_path"])
                        item["tenders"].append({"category": item["category"], "sub_category": item["sub_category"],
                                                "keyword": keyword, "href": row["href"], "id": row["id"], **details})
                except Exception as e:  # keep tenders already collected; move on to the next keyword
                    item["error"] = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
                    log(f"ERROR {where}: {item['error']} ({len(item['tenders'])} tenders kept)")
                failed = [t for t in item["tenders"] if not t["zip_path"]]
                if failed and any_zip:
                    for tender in failed:
                        try:
                            details = tender_details(context, tender["href"], tender.get("Tender ID") or tender["id"])
                            if details:
                                tender["zip_path"] = details["zip_path"]
                        except Exception as e:
                            _problem(tender.get("Tender ID") or tender["id"], f"retry failed: {type(e).__name__}")
                for tender in item["tenders"]:
                    _finish(tender, extract_and_upload)
                if item["tenders"]:
                    log_block(where, item["tenders"])
                finish(item)
                done = ki
            browser.close()
    except Exception as e:  # browser crash: the other sub-categories keep going
        err = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
        log(f"ERROR {label}: browser crashed, {len(group) - done} keyword(s) not searched: {err}")
        for item in group[done:]:
            item["error"] = item["error"] or f"browser crashed: {err}"
            finish(item)
    finally:
        _local.ctx = ""


def scrape(portals: list[str], only_keyword: str | None = None, headless: bool = False,
           on_keyword=None, days: int = 0) -> list[dict]:
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
    dates = published_window(days)  # today, plus `days` older days when the job asks for them

    def finish(item) -> None:
        with seen_lock:
            stats[0] += 1
            stats[1] += len(item["tenders"])
        progress(f"{stats[0]}/{len(keywords)} keywords, {stats[1]} tenders")
        if on_keyword:
            on_keyword(item)

    for portal in portals:
        stats = [0, 0]  # keywords finished, tenders found on this portal
        portal_items = [{"portal": portal, "category": c, "sub_category": s, "keyword": k,
                         "tenders": [], "error": None} for c, s, k in keywords]
        items += portal_items
        groups = {}
        for item in portal_items:
            groups.setdefault((item["category"], item["sub_category"]), []).append(item)
        with ThreadPoolExecutor(max_workers=max(len(groups), 1)) as pool:
            futures = [pool.submit(_scrape_group, portal, g, seen, seen_lock, headless, extract_and_upload, finish,
                                   dates) for g in groups.values()]
            for f in futures:
                f.result()
    return items


def run(only_keyword: str | None = None) -> None:
    """Manual run: `python -m nic_automation [keyword]` prints each keyword's array as soon as it's done."""
    only_keyword = only_keyword or (sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.reconfigure(errors="replace")  # page fields contain ₹, which crashes a cp1252 console

    def show(item):
        if item["tenders"]:
            print(json.dumps(item["tenders"], ensure_ascii=False, indent=2), flush=True)

    started = time.monotonic()
    items = scrape(website, only_keyword, on_keyword=show)
    for portal in website:
        log_summary(portal, [i for i in items if i["portal"] == portal], [], window_label(published_window()),
                    (time.monotonic() - started) / 60)
