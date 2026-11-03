"""NIC_DOWNLOAD queue self-check. No browser, no MQ, no network: fetcher, channel and emit are stubbed.

Run: uv run python -m automation_v2.test_nic_fetch
"""
import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from automation_v2 import consume, dispatch  # noqa: E402
from automation_v2.dispatch import Requeue  # noqa: E402
from automation_v2.schemas import fetch_adapter  # noqa: E402

sent = []
dispatch.emit = lambda cid, event, data: sent.append((cid, event, data))


class Ch:
    def __init__(self):
        self.published, self.acked, self.nacked = [], [], []

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append((exchange, routing_key, body))

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag, requeue):
        self.nacked.append(delivery_tag)


class Method:
    delivery_tag, routing_key = 7, "automation-v2:tasks"


P = "https://wbtenders.gov.in"
body = json.dumps({"type": "NIC_DOWNLOAD", "referenceNo": "2026_X_1", "portal": P, "client_id": "whk_test"}).encode()
FILES = {"files": [{"name": "BOQ.xls", "url": "https://s3/x"}], "bidStatus": None}


def not_found(job):
    raise Requeue("not found")


# documents not got: same message to the end of the same queue, acked, no webhook
ch = Ch()
consume.handle(ch, Method, body, "file.fetched", fetch_adapter, {"NIC_DOWNLOAD": not_found})
assert ch.published == [("", "automation-v2:tasks", body)] and ch.acked == [7] and not ch.nacked, vars(ch)
assert sent == [], sent

# got them: one file.fetched_success to client_id, acked, nothing republished
ch = Ch()
consume.handle(ch, Method, body, "file.fetched", fetch_adapter, {"NIC_DOWNLOAD": lambda job: FILES})
assert ch.published == [] and ch.acked == [7], vars(ch)
assert sent == [("whk_test", "file.fetched_success",
                 {"type": "NIC_DOWNLOAD", "referenceNo": "2026_X_1", "portal": P, "result": FILES, "error": None})], sent
assert fetch_adapter.validate_python(json.loads(body)).portal == P

# message without a valid portal: rejected, failed webhook, nacked
for bad in ({"type": "NIC_DOWNLOAD", "referenceNo": "2026_X_1", "client_id": "whk_test"},
            {"type": "NIC_DOWNLOAD", "referenceNo": "2026_X_1", "portal": "wbtenders.gov.in", "client_id": "whk_test"}):
    sent.clear()
    ch = Ch()
    consume.handle(ch, Method, json.dumps(bad).encode(), "file.fetched", fetch_adapter, {"NIC_DOWNLOAD": lambda job: FILES})
    assert ch.nacked == [7] and [e for _, e, _ in sent] == ["file.fetched_failed"], (bad, vars(ch), sent)

# other fetch types still validate without a portal
assert fetch_adapter.validate_python({"type": "GEM_DOWNLOAD", "referenceNo": "GEM/1"}).referenceNo == "GEM/1"

# any other error still fails as before: failed webhook, nacked
sent.clear()
ch = Ch()
consume.handle(ch, Method, body, "file.fetched", fetch_adapter, {"NIC_DOWNLOAD": lambda job: 1 / 0})
assert ch.nacked == [7] and not ch.published and [e for _, e, _ in sent] == ["file.fetched_failed"], (vars(ch), sent)

# tags: BOQ Excel -> boqComparativeChart, everything else -> tenderDocument
from automation_v2.nic_fetch import _tag  # noqa: E402
assert _tag("tenders/2026_X_1/BOQ_123.xls") == "boqComparativeChart"
assert _tag("tenders/2026_X_1/boq.XLSX") == "boqComparativeChart"
assert _tag("tenders/2026_X_1/NIT.pdf") == "tenderDocument"
assert _tag("tenders/2026_X_1/BOQ.pdf") == "tenderDocument"

print("ok")
