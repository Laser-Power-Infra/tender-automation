"""Scrape NIC eProcure portals for every configured keyword and send each keyword's tenders as one
nic.synced_* webhook to the job's client_id. Then, per portal, the "Tenders by Organisation" flow finds
tenders whose title is just their reference number (keyword search can't find those) and sends one
nic.synced_* per organisation. Jobs come from V2_SYNC_QUEUE (consume_tender_sync_v2).
"""
import logging
import sys
import time
from pathlib import Path

from django.conf import settings

from . import dispatch

sys.path.insert(0, str(Path(__file__).parent / "nic_automation" / "src"))
from nic_automation.org_scraper import scrape_untitled  # noqa: E402
from nic_automation.scraper import log_summary, published_window, scrape, window_label  # noqa: E402

logger = logging.getLogger(__name__)


def _send(client_id: str, items: list[dict]) -> None:
    """One event per item: data = {"type": "NIC_SYNC", "portal", "result": [tenders], "error"}."""
    for it in items:
        with dispatch.job_events("nic.synced", client_id, type="NIC_SYNC", portal=it["portal"]) as outcome:
            if it["error"]:
                outcome.fail(it["error"], it["tenders"])
            else:
                outcome.succeed(it["tenders"])


def run(client_id: str, portals: list[str], days: int = 0) -> None:
    """`days`: older days to include besides today (0 = tenders e-Published today only), for both flows."""
    # Same design as fetch.py / sync_result.py: the webhook goes out after the browser is closed.
    # Inside sync_playwright the thread runs an asyncio loop, and Django refuses DB queries (the webhook
    # lookup) there with SynchronousOnlyOperation. So: scrape one portal, close its browser, send its results.
    for portal in portals:
        started, got, crashed = time.monotonic(), {}, []
        for flow, step in (("keywords", lambda: scrape([portal], headless=settings.HEADLESS_BROWSER, days=days)),
                           ("by organisation",
                            lambda: scrape_untitled(portal, headless=settings.HEADLESS_BROWSER, days=days))):
            try:
                items = step()
            except Exception as e:  # browser crash etc.: report it for this portal and go on
                logger.exception("NIC %s scrape crashed portal=%s", flow, portal)
                crashed.append(f"{flow}: scrape crashed: {type(e).__name__}: {e}")
                dispatch.emit(client_id, "nic.synced_failed",
                              {"type": "NIC_SYNC", "portal": portal, "result": None, "error": f"{type(e).__name__}: {e}"})
                continue
            got[flow] = items
            _send(client_id, items)
        log_summary(portal, got.get("keywords", []), got.get("by organisation", []),
                    window_label(published_window(days)), (time.monotonic() - started) / 60, crashed)
