import json
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from automation_v2 import nic_sync
from automation_v2.consume import get_channel
from automation_v2.dispatch import client_id_from
from automation_v2.schemas import sync_adapter

logger = logging.getLogger(__name__)


def on_message(ch, method, _properties, body: bytes) -> None:
    try:
        raw = json.loads(body)
        client_id = client_id_from(raw)
        if not client_id:
            raise ValueError("client_id is required")
        job = sync_adapter.validate_python(raw)
    except Exception:
        logger.exception("Bad sync job dropped: %r", body[:200])  # no valid client_id/portals: nobody to notify
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return
    # shortcut: ack before the run; a scrape of all keywords outlives the pika heartbeat, so a late ack fails.
    # A crash is still reported as nic.synced_failed but not redelivered; run in a thread with heartbeats if that matters.
    ch.basic_ack(delivery_tag=method.delivery_tag)
    logger.info("Sync start client_id=%s portals=%s", client_id, job.portals)
    try:
        nic_sync.run(client_id, job.portals)
        logger.info("Sync done client_id=%s", client_id)
    except Exception:
        logger.exception("Sync failed client_id=%s", client_id)


class Command(BaseCommand):
    help = "v2: scrape NIC portals from the sync queue and emit nic.synced_* webhooks per keyword"

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        channel = get_channel(settings.V2_SYNC_QUEUE)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=settings.V2_SYNC_QUEUE, on_message_callback=on_message)
        logger.info("Listening on %s", settings.V2_SYNC_QUEUE)
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
            channel.connection.close()
