"""nic_sync self-check. No browser, no DB, no network: scrape and emit are stubbed.

Run: uv run python -m automation_v2.test_nic_sync
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from automation_v2 import dispatch, nic_sync  # noqa: E402
from automation_v2.events import WEBHOOK_EVENTS  # noqa: E402
from automation_v2.schemas import sync_adapter  # noqa: E402

P = "https://etender.up.nic.in"
sent = []

assert "nic.synced_success" in WEBHOOK_EVENTS and "nic.synced_failed" in WEBHOOK_EVENTS

# one event per keyword, sent only after scrape() returned (browser closed, like fetch.py / sync_result.py)
tender = {"Tender ID": "2026_X_1", "Tenders Documents": [{"name": "BOQ.xls", "url": "https://s3/x"}]}
ITEMS = [
    {"portal": P, "category": "Manufacturing", "sub_category": "Cables", "keyword": "Cable", "tenders": [tender], "error": None},
    {"portal": P, "category": "EPC", "sub_category": "Solar", "keyword": "Solar PV", "tenders": [],
     "error": "no result table (search captcha?)"},
]
scraping = False


def emit(cid, event, data):
    assert not scraping, "webhook sent while the browser is open (Django refuses DB queries there)"
    sent.append((cid, event, data))


dispatch.emit = emit


days_seen = []  # (flow, days) each scrape was given


def fake_scrape(portals, headless, days):
    global scraping
    days_seen.append(("keywords", days))
    scraping = True
    try:
        if portals == ["https://dead.example.in"]:
            raise RuntimeError("browser died")
        return [dict(it, portal=portals[0]) for it in ITEMS]
    finally:
        scraping = False


untitled = {"Tender ID": "2026_X_9", "organisation": "Agra Development Authority", "keyword": None,
            "Tenders Documents": [{"name": "NIT.pdf", "url": "https://s3/y"}]}
flows = []


def fake_untitled(portal, headless, days):
    global scraping
    flows.append(("org", portal))
    days_seen.append(("org", days))
    scraping = True
    try:
        if portal == "https://dead.example.in":
            raise RuntimeError("org page died")
        return [{"portal": portal, "organisation": "Agra Development Authority", "tenders": [untitled], "error": None}]
    finally:
        scraping = False


nic_sync.scrape = fake_scrape
nic_sync.scrape_untitled = fake_untitled
nic_sync.run("whk_test", [P])
# keyword events first, then one event per organisation with untitled tenders
assert [e for _, e, _ in sent] == ["nic.synced_success", "nic.synced_failed", "nic.synced_success"], sent
assert sent[0] == ("whk_test", "nic.synced_success", {"type": "NIC_SYNC", "portal": P, "result": [tender], "error": None})
assert sent[1][2] == {"type": "NIC_SYNC", "portal": P, "result": [], "error": "no result table (search captcha?)"}
assert sent[2][2] == {"type": "NIC_SYNC", "portal": P, "result": [untitled], "error": None}

# one portal crashing: one failed event per crashed flow, and the next portal still runs both flows
sent.clear()
nic_sync.run("whk_test", ["https://dead.example.in", P])
assert [e for _, e, _ in sent] == ["nic.synced_failed", "nic.synced_failed",
                                   "nic.synced_success", "nic.synced_failed", "nic.synced_success"], sent
assert sent[0][2] == {"type": "NIC_SYNC", "portal": "https://dead.example.in", "result": None,
                      "error": "RuntimeError: browser died"}
assert sent[1][2]["error"] == "RuntimeError: org page died"

# days: default 0 (today only), and a job's days reach both flows
assert days_seen and all(d == 0 for _, d in days_seen), days_seen
days_seen.clear()
nic_sync.run("whk_test", [P], 2)
assert days_seen == [("keywords", 2), ("org", 2)], days_seen

# payload validation
assert sync_adapter.validate_python({"client_id": "whk_x", "portals": [P]}).portals == [P]
assert sync_adapter.validate_python({"portals": [P]}).days == 0
assert sync_adapter.validate_python({"portals": [P], "days": 2}).days == 2
for bad in ({"portals": []}, {"portals": ["etender.up.nic.in"]}, {}, {"portals": [P], "days": -1}):
    try:
        sync_adapter.validate_python(bad)
        raise AssertionError(f"should reject {bad}")
    except ValueError:
        pass

# log layout: one block per search that found tenders, then the per-website table by category
import contextlib  # noqa: E402
import io  # noqa: E402
import re  # noqa: E402

from nic_automation.scraper import log_block, log_summary  # noqa: E402  (nic_sync put its folder on sys.path)

out = io.StringIO()
with contextlib.redirect_stdout(out):
    log_block("EPC > Cable", [
        {"reference_no": "2026_X_1", "Tenders Documents": [{"name": "BOQ.xls", "url": "https://s3/x"}]},
        {"reference_no": "2026_X_2", "Tenders Documents": []}])
    log_summary(P, ITEMS, [{"portal": P, "organisation": "Agra", "tenders": [untitled], "error": None}],
                "24-Nov-2026", 1.5, ["by organisation: scrape crashed: X"])
text = out.getvalue()
assert ("  EPC > Cable\n    2 tenders found\n    2026_X_1   1 file\n        BOQ.xls   https://s3/x\n"
        "    2026_X_2   NO FILES (") in text, text
assert "  etender.up.nic.in  SUMMARY  24-Nov-2026  (1.5 min)\n" in text, text
for row in (r"Manufacturing\s+1 kw\s+1\s+1\n", r"EPC\s+1 kw\s+0\s+0\n", r"UNTITLED\s+-\s+1\s+1\n", r"TOTAL\s+2\s+2\n"):
    assert re.search(row, text), (row, text)
assert "Errors: 2\n        EPC > Solar PV: no result table (search captcha?)\n" in text, text

print("ok")
