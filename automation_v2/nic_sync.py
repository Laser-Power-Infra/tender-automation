"""Scrape NIC eProcure portals for every configured keyword and send each keyword's tenders as one
tender.synced_* webhook to the job's client_id. Jobs come from V2_SYNC_QUEUE (consume_tender_sync_v2).
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
    def send(it) -> None:
        """Called by scrape() as soon as a keyword is done: one event, data.result = its tender array."""
        event = "tender.synced_failed" if it["error"] else "tender.synced_success"
        log(f"webhook {event} -> client_id={client_id} ({len(it['tenders'])} tenders)")
        # dispatch logs the outcome next: Webhook sent ... status= / delivery failed / No active subscription
        with dispatch.job_events("tender.synced", client_id, portal=it["portal"], category=it["category"],
                                 sub_category=it["sub_category"], keyword=it["keyword"]) as outcome:
            if it["error"]:
                outcome.fail(it["error"], it["tenders"])
            else:
                outcome.succeed(it["tenders"])

    try:
        scrape(portals, headless=settings.HEADLESS_BROWSER, on_keyword=send)
    except Exception as e:  # browser crash etc.: keywords already sent stay sent; report the crash per portal
        for portal in portals:
            dispatch.emit(client_id, "tender.synced_failed",
                          {"portal": portal, "result": None, "error": f"{type(e).__name__}: {e}"})
        raise
