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
dispatch.emit = lambda cid, event, data: sent.append((cid, event, data))
assert "tender.synced_success" in WEBHOOK_EVENTS and "tender.synced_failed" in WEBHOOK_EVENTS

# one event per keyword; a tender without documents (captcha failed) is still a success
tender = {"Tender ID": "2026_X_1", "Tenders Documents": [{"name": "NIT.pdf", "url": None}]}
nic_sync.scrape = lambda portals, headless: [
    {"portal": P, "category": "Manufacturing", "sub_category": "Cables", "keyword": "Cable", "tenders": [tender], "error": None},
    {"portal": P, "category": "EPC", "sub_category": "Solar", "keyword": "Solar PV", "tenders": [],
     "error": "no result table (search captcha?)"},
]
nic_sync.run("whk_test", [P])
assert [e for _, e, _ in sent] == ["tender.synced_success", "tender.synced_failed"], sent
assert sent[0] == ("whk_test", "tender.synced_success", {"portal": P, "category": "Manufacturing", "sub_category": "Cables",
                                                          "keyword": "Cable", "result": [tender], "error": None})
assert sent[1][2]["error"] == "no result table (search captcha?)" and sent[1][2]["keyword"] == "Solar PV"

# scrape crash: one failed event per portal, error re-raised
sent.clear()


def boom(portals, headless):
    raise RuntimeError("browser died")


nic_sync.scrape = boom
try:
    nic_sync.run("whk_test", [P, "https://eproc.example.nic.in"])
    raise AssertionError("crash should re-raise")
except RuntimeError:
    pass
assert [(e, d["portal"]) for _, e, d in sent] == [("tender.synced_failed", P),
                                                   ("tender.synced_failed", "https://eproc.example.nic.in")], sent

# payload validation
assert sync_adapter.validate_python({"client_id": "whk_x", "portals": [P]}).portals == [P]
for bad in ({"portals": []}, {"portals": ["etender.up.nic.in"]}, {}):
    try:
        sync_adapter.validate_python(bad)
        raise AssertionError(f"should reject {bad}")
    except ValueError:
        pass

print("ok")
