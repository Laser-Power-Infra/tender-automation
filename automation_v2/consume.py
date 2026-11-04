"""Shared RabbitMQ consumer loop for the v2 workers.

One message = one job = exactly one webhook event. A handler returns the result
(success) or raises (failure). No job publishes to another queue.
"""
import json
import logging
import os
import threading

import pika
from django.conf import settings

from .dispatch import Requeue, client_id_from, job_events

logger = logging.getLogger(__name__)


def get_channel(queue: str):
    channel = pika.BlockingConnection(pika.URLParameters(settings.MQ_URL)).channel()
    channel.queue_declare(queue=queue, durable=True)
    return channel


def run_keeping_alive(connection, fn):
    """Run fn() in a thread while this thread keeps answering broker heartbeats; returns its result or re-raises.
    A long job run directly in the consumer callback blocks heartbeats, the broker drops the connection and the
    later ack fails (StreamLostError). Acks/publishes stay on this thread: pika objects aren't thread-safe."""
    box = {}

    def target():
        from django.db import connections
        try:
            box["result"] = fn()
        except BaseException as e:
            box["error"] = e
        finally:
            connections.close_all()  # this thread's DB connection (webhook lookup in dispatch.emit)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    while worker.is_alive():
        connection.process_data_events(time_limit=1)
    if "error" in box:
        raise box["error"]
    return box.get("result")


def handle(ch, method, body: bytes, base: str, adapter, handlers: dict) -> None:
    try:
        raw = json.loads(body)
        if not isinstance(raw, dict):
            raise ValueError("payload is not a JSON object")
    except Exception:
        # No payload means no ids and no client_id, so there is nobody to notify.
        logger.exception("Undecodable message dropped: %r", body[:200])
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return
    ids = {"type": raw.get("type"), "referenceNo": raw.get("referenceNo")}
    if base == "file.parsed":
        ids["file_link"] = raw.get("file_link")  # echoed so receivers can match the event to the file they sent
    if base == "file.fetched" and raw.get("type") == "NIC_DOWNLOAD":
        ids["portal"] = raw.get("portal")  # same reference no. can exist on two NIC portals
    def work():
        with job_events(base, client_id_from(raw), **ids) as outcome:
            job = adapter.validate_python(raw)
            logger.info("Job start type=%s referenceNo=%s", job.type, job.referenceNo)
            outcome.succeed(handlers[job.type](job))
        logger.info("Job done type=%s referenceNo=%s", job.type, job.referenceNo)

    try:
        # prefetch_count=1 and this message is unacked, so no other delivery arrives while we wait
        run_keeping_alive(ch.connection, work)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Requeue as e:
        # shortcut: no retry limit (user's choice); a job that never succeeds cycles through the queue forever
        logger.info("Job requeued to the end of %s: %s payload=%s", method.routing_key, e, raw)
        ch.basic_publish("", method.routing_key, body, pika.BasicProperties(delivery_mode=2, content_type="application/json"))
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        # ponytail: nack without requeue or DLX drops the message, same as legacy; add a DLX if replay matters
        logger.exception("Job failed payload=%s", raw)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def serve(queue: str, base: str, adapter, handlers: dict) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    os.makedirs(settings.TENDER_PARSING_TEMP_DIR, exist_ok=True)
    channel = get_channel(queue)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue, on_message_callback=lambda ch, m, _p, body: handle(ch, m, body, base, adapter, handlers))
    logger.info("Listening on %s (event %s_*)", queue, base)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        channel.connection.close()
