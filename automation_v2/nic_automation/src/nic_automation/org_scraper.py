"""Untitled tenders via "Tenders by Organisation".

Some tenders have no real title: the title is just their Tender Reference Number, so the keyword search
never finds them. This walks every organisation's tender list on a portal, picks those tenders and runs the
same steps as the keyword flow (details page -> captcha -> zip -> unzip -> S3).

Manual run (prints each tender's S3 links):
  python -m nic_automation.org_scraper https://etender.up.nic.in
"""
import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from nic_automation.captcha_decoder import _model
from nic_automation.scraper import (MAX_PAGES, NEXT_PAGE, ORGS_SEARCHED, _finish, _local, _problem, _use_v2_lib, log,
                                    log_block, log_summary, progress, published_col, published_date,
                                    published_window, tender_details, window_label)

ORG_LINK = 'a[title="Tenders by Organisation"]'


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().strip("[]").strip().lower()


def is_untitled(title: str, ref_no: str) -> bool:
    """True when the tender's title is empty or just its reference number."""
    return not _norm(title) or _norm(title) == _norm(ref_no)


def _organisations(page) -> list[tuple[str, str]]:
    """(name, tender list url) of every organisation with a count link."""
    orgs = []
    for tr in page.locator("#table tr.even, #table tr.odd").all():
        tds = tr.locator("td")
        link = tr.locator("a.link2")
        if tds.count() >= 3 and link.count():
            orgs.append((tds.nth(1).inner_text().strip(), urljoin(page.url, link.first.get_attribute("href"))))
    return orgs


def _untitled_rows(page, dates, name: str = "") -> list[dict]:
    """Untitled tenders e-Published on one of `dates` on the current list page: {"id", "ref", "href"}."""
    rows = []
    col = published_col(page)
    trs = page.locator("#table tr.even, #table tr.odd").all()
    for i, tr in enumerate(trs):
        if i and i % 500 == 0:  # a big list takes minutes: show it is not stuck
            log(f"UNTITLED > {name}: reading a big list, {i}/{len(trs)} rows, {len(rows)} untitled so far")
        link = tr.locator("a[title='View Tender Information']")
        tds = tr.locator("td")
        if not link.count() or tds.count() <= max(col, 4):
            continue
        if published_date(tds.nth(col).inner_text()) not in dates:
            continue
        title = link.first.inner_text()
        rest = tds.nth(4).inner_text().replace(title, "")
        refs = re.findall(r"\[([^\]]*)\]", rest)  # [ref no][tender id]
        if len(refs) >= 2 and is_untitled(title, refs[-2]):
            rows.append({"id": refs[-1].strip(), "ref": refs[-2].strip(),
                         "href": urljoin(page.url, link.first.get_attribute("href"))})
    return rows


def scrape_untitled(portal: str, headless: bool = False, on_org=None, days: int = 0) -> list[dict]:
    """One item per organisation with untitled tenders (or an error): {portal, organisation, tenders, error}.
    Portal-level failure -> a single item with organisation None. `on_org(item)` is called as each finishes."""
    _use_v2_lib()
    from automation_v2.lib.zip_utils import extract_and_upload
    _model()
    host = urlparse(portal).netloc
    _local.ctx = host
    dates = published_window(days)  # today, plus `days` older days when the job asks for them
    items, seen = [], set()
    any_zip = False

    def finish(item):
        items.append(item)
        if on_org:
            on_org(item)

    chrome = os.environ.get("CHROME_PATH")  # the Docker image ships /usr/bin/chromium, not Playwright's build
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless,
                                        executable_path=chrome if chrome and os.path.exists(chrome) else None)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(portal)
                page.locator(ORG_LINK).first.click(timeout=30_000)
                page.wait_for_selector("#table", timeout=30_000)
                orgs = _organisations(page)
            except Exception as e:
                err = f"no 'Tenders by Organisation' list: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
                log(f"ERROR UNTITLED: {err}")
                finish({"portal": portal, "organisation": None, "tenders": [], "error": err})
                browser.close()
                return items
            ORGS_SEARCHED[portal] = len(orgs)
            for oi, (name, href) in enumerate(orgs, 1):
                item = {"portal": portal, "organisation": name, "tenders": [], "error": None}
                try:
                    page.goto(href)
                    page.wait_for_load_state()
                    rows, pages = [], 0
                    while pages < MAX_PAGES:
                        pages += 1
                        rows += [r for r in _untitled_rows(page, dates, name) if r["id"] not in seen]
                        nxt = page.locator(NEXT_PAGE)
                        if not nxt.count():
                            break
                        nxt.first.click()
                        page.wait_for_load_state()
                    for row in rows:
                        seen.add(row["id"])
                        details = tender_details(context, row["href"], row["id"])
                        if details is None:
                            continue
                        any_zip = any_zip or bool(details["zip_path"])
                        item["tenders"].append({"category": "SPECIAL", "sub_category": None, "keyword": None,
                                                "organisation": name, "href": row["href"], "id": row["id"],
                                                **details})
                except Exception as e:  # keep what was collected; go on with the next organisation
                    item["error"] = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
                    log(f"ERROR UNTITLED > {name}: {item['error']} ({len(item['tenders'])} tenders kept)")
                for tender in [t for t in item["tenders"] if not t["zip_path"]] if any_zip else []:
                    try:  # once one captcha passed, the session usually downloads without one
                        details = tender_details(context, tender["href"], tender.get("Tender ID") or tender["id"])
                        if details:
                            tender["zip_path"] = details["zip_path"]
                    except Exception as e:
                        _problem(tender.get("Tender ID") or tender["id"], f"retry failed: {type(e).__name__}")
                for tender in item["tenders"]:
                    _finish(tender, extract_and_upload)
                if item["tenders"]:
                    log_block(f"UNTITLED > {name}", item["tenders"])
                if item["tenders"] or item["error"]:
                    finish(item)
                progress(f"{oi}/{len(orgs)} organisations, {sum(len(i['tenders']) for i in items)} untitled tenders")
            browser.close()
    except Exception as e:  # browser crash: report it once for the portal
        err = f"browser crashed: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
        log(f"ERROR UNTITLED: {err}")
        finish({"portal": portal, "organisation": None, "tenders": [], "error": err})
    finally:
        _local.ctx = ""
    return items


assert is_untitled("[DM/Garia/Tender/2026-27/1850]", "DM/Garia/Tender/2026-27/1850")
assert is_untitled(" [ dm/garia/tender/2026-27/1850 ] ", "DM/Garia/Tender/2026-27/1850")
assert is_untitled("[]", "X/1")
assert not is_untitled("[Theme painting work on metro pillars]", "20/2026-27")


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")  # page fields contain ₹, which crashes a cp1252 console
    if len(sys.argv) != 2:
        sys.exit("usage: python -m nic_automation.org_scraper <portal>")

    def show(item):
        if item["error"]:
            print(f"{item['organisation']}: ERROR {item['error']}", flush=True)
        for t in item["tenders"]:
            print(json.dumps({"organisation": t["organisation"], "Tender ID": t.get("Tender ID"),
                              "documents": [d["url"] for d in t["Tenders Documents"]]}, ensure_ascii=False), flush=True)

    started = time.monotonic()
    found = scrape_untitled(sys.argv[1], headless=os.environ.get("HEADLESS", "1") != "0", on_org=show)
    log_summary(sys.argv[1], [], found, window_label(published_window()), (time.monotonic() - started) / 60)
