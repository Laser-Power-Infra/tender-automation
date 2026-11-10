"""Scrape NIC eProcure portals for every configured keyword and send each keyword's tenders as one
nic.synced_* webhook to the job's client_id. Then, per portal, the "Tenders by Organisation" flow finds
tenders whose title is just their reference number (keyword search can't find those) and sends one
nic.synced_* per organisation. Jobs come from V2_SYNC_QUEUE (consume_tender_sync_v2).
"""
import logging
import sys
from pathlib import Path

from django.conf import settings

from . import dispatch

sys.path.insert(0, str(Path(__file__).parent / "nic_automation" / "src"))
from nic_automation.org_scraper import scrape_untitled  # noqa: E402
from nic_automation.scraper import log, scrape  # noqa: E402

logger = logging.getLogger(__name__)


def _send(client_id: str, items: list[dict], label: str) -> None:
    """One event per item: data = {"type": "NIC_SYNC", "portal", "result": [tenders], "error"}."""
    for it in items:
        event = "nic.synced_failed" if it["error"] else "nic.synced_success"
        log(f"[{it['portal']}] '{it.get(label)}' webhook {event} -> client_id={client_id} ({len(it['tenders'])} tenders)")
        # dispatch logs the outcome next: Webhook sent ... status= / delivery failed / No active subscription
        with dispatch.job_events("nic.synced", client_id, type="NIC_SYNC", portal=it["portal"]) as outcome:
            if it["error"]:
                outcome.fail(it["error"], it["tenders"])
            else:
                outcome.succeed(it["tenders"])


def run(client_id: str, portals: list[str]) -> None:
    # Same design as fetch.py / sync_result.py: the webhook goes out after the browser is closed.
    # Inside sync_playwright the thread runs an asyncio loop, and Django refuses DB queries (the webhook
    # lookup) there with SynchronousOnlyOperation. So: scrape one portal, close its browser, send its results.
    for portal in portals:
        for flow, label, step in (("keywords", "keyword", lambda: scrape([portal], headless=settings.HEADLESS_BROWSER)),
                                  ("by organisation", "organisation",
                                   lambda: scrape_untitled(portal, headless=settings.HEADLESS_BROWSER))):
            try:
                items = step()
            except Exception as e:  # browser crash etc.: report it for this portal and go on
                logger.exception("NIC %s scrape crashed portal=%s", flow, portal)
                log(f"[{portal}] webhook nic.synced_failed -> client_id={client_id} ({flow} crashed)")
                dispatch.emit(client_id, "nic.synced_failed",
                              {"type": "NIC_SYNC", "portal": portal, "result": None, "error": f"{type(e).__name__}: {e}"})
                continue
            _send(client_id, items, label)
