"""Scrape NIC eProcure portals for every configured keyword and send each keyword's tenders as one
nic.synced_* webhook to the job's client_id. Jobs come from V2_SYNC_QUEUE (consume_tender_sync_v2).
"""
import logging
import sys
from pathlib import Path

from django.conf import settings

from . import dispatch

sys.path.insert(0, str(Path(__file__).parent / "nic_automation" / "src"))
from nic_automation.scraper import log, scrape  # noqa: E402

logger = logging.getLogger(__name__)


def run(client_id: str, portals: list[str]) -> None:
    # Same design as fetch.py / sync_result.py: the webhook goes out after the browser is closed.
    # Inside sync_playwright the thread runs an asyncio loop, and Django refuses DB queries (the webhook
    # lookup) there with SynchronousOnlyOperation. So: scrape one portal, close its browser, send its keywords.
    for portal in portals:
        try:
            items = scrape([portal], headless=settings.HEADLESS_BROWSER)
        except Exception as e:  # browser crash etc.: report it for this portal and go on with the next one
            logger.exception("NIC scrape crashed portal=%s", portal)
            log(f"[{portal}] webhook nic.synced_failed -> client_id={client_id} (portal crashed)")
            dispatch.emit(client_id, "nic.synced_failed",
                          {"type": "NIC_SYNC", "result": None, "error": f"{type(e).__name__}: {e}"})
            continue
        for it in items:  # one event per keyword: data = {"type": "NIC_SYNC", "result": [tenders], "error"}
            event = "nic.synced_failed" if it["error"] else "nic.synced_success"
            log(f"[{it['portal']}] '{it['keyword']}' webhook {event} -> client_id={client_id} "
                f"({len(it['tenders'])} tenders)")
            # dispatch logs the outcome next: Webhook sent ... status= / delivery failed / No active subscription
            with dispatch.job_events("nic.synced", client_id, type="NIC_SYNC") as outcome:
                if it["error"]:
                    outcome.fail(it["error"], it["tenders"])
                else:
                    outcome.succeed(it["tenders"])
