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

assert "tender.synced_success" in WEBHOOK_EVENTS and "tender.synced_failed" in WEBHOOK_EVENTS

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


def fake_scrape(portals, headless):
    global scraping
    scraping = True
    try:
        if portals == ["https://dead.example.in"]:
            raise RuntimeError("browser died")
        return [dict(it, portal=portals[0]) for it in ITEMS]
    finally:
        scraping = False


nic_sync.scrape = fake_scrape
nic_sync.run("whk_test", [P])
assert [e for _, e, _ in sent] == ["tender.synced_success", "tender.synced_failed"], sent
assert sent[0] == ("whk_test", "tender.synced_success", {"portal": P, "category": "Manufacturing", "sub_category": "Cables",
                                                          "keyword": "Cable", "result": [tender], "error": None})
assert sent[1][2]["error"] == "no result table (search captcha?)" and sent[1][2]["keyword"] == "Solar PV"

# one portal crashing: one failed event for it, and the next portal still runs
sent.clear()
nic_sync.run("whk_test", ["https://dead.example.in", P])
assert [(e, d["portal"]) for _, e, d in sent] == [("tender.synced_failed", "https://dead.example.in"),
                                                   ("tender.synced_success", P), ("tender.synced_failed", P)], sent
assert sent[0][2]["error"] == "RuntimeError: browser died"

# payload validation
assert sync_adapter.validate_python({"client_id": "whk_x", "portals": [P]}).portals == [P]
for bad in ({"portals": []}, {"portals": ["etender.up.nic.in"]}, {}):
    try:
        sync_adapter.validate_python(bad)
        raise AssertionError(f"should reject {bad}")
    except ValueError:
        pass

print("ok")
