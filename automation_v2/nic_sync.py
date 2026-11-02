"""Scrape NIC eProcure portals for every configured keyword and send each keyword's tenders as one
tender.synced_* webhook to the job's client_id. Jobs come from V2_SYNC_QUEUE (consume_tender_sync_v2).
"""
import logging
import sys
from pathlib import Path

from django.conf import settings

from . import dispatch

sys.path.insert(0, str(Path(__file__).parent / "nic_automation" / "src"))
from nic_automation.scraper import scrape  # noqa: E402

logger = logging.getLogger(__name__)


def run(client_id: str, portals: list[str]) -> None:
    try:
        items = scrape(portals, headless=settings.HEADLESS_BROWSER)
    except Exception as e:  # browser crash etc.: nothing per keyword to send, so one failed event per portal
        for portal in portals:
            dispatch.emit(client_id, "tender.synced_failed",
                          {"portal": portal, "result": None, "error": f"{type(e).__name__}: {e}"})
        raise
    for it in items:  # one event per keyword; data.result is that keyword's tender array
        with dispatch.job_events("tender.synced", client_id, portal=it["portal"], category=it["category"],
                                 sub_category=it["sub_category"], keyword=it["keyword"]) as outcome:
            if it["error"]:
                outcome.fail(it["error"], it["tenders"])
            else:
                outcome.succeed(it["tenders"])
