import json
import logging
from pathlib import Path

import pika
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from tender_search.queue import get_channel
from tender_search.queue_types import (
    GemDownloadTask,
    NonGemDownloadTask,
    RAGemDownloadTask,
    tender_tasks_adapter,
)
from tender_search.services.non_gem_tender_pdf_downloader import login_tender247
from tender_search.services.tender_tiger import login_tiger
from tender_search.models import TenderMerged, TenderFiles
from tender_search.services.gem_pdf_downloader import download_gem_pdf
from tender_search.services.gem_ra_pdf_downloader import download_ra_pdf
logger = logging.getLogger(__name__)
import asyncio

if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def callback(ch, method, properties, body):
    try:
        raw = json.loads(body)
        payload = tender_tasks_adapter.validate_python(raw)
        logger.info(
            "[tender:tasks] Received type=%s payload=%s",
            payload.type,
            body.decode(),
        )
        print(f"[tender:tasks] Received: type={payload.type} payload={raw}")

        if isinstance(payload, GemDownloadTask):
            gem_result = download_gem_pdf(payload.referenceNo)
            print("GEM_RESULT.....................", gem_result)

            if gem_result.get("success"):
                ch.basic_publish(
                    exchange="",
                    routing_key=settings.TENDER_PARSING_QUEUE,
                    body=json.dumps({"type": "GEM_PDF_PARSING", "referenceNo": payload.gemId}),
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                logger.info("Published GEM parsing job for %s", payload.gemId)
            else:
                logger.error("GEM_DOWNLOAD failed for %s: %s", payload.gemId, gem_result.get("error"))

            ch.basic_ack(delivery_tag=method.delivery_tag)
        elif isinstance(payload, RAGemDownloadTask):
            ra_result = download_ra_pdf(payload.referenceNo)
            print("RA_RESULT.....................", ra_result)

            if ra_result.get("success"):
                ch.basic_publish(
                    exchange="",
                    routing_key=settings.TENDER_PARSING_QUEUE,
                    body=json.dumps({"type": "RA_GEM_PDF_PARSING", "referenceNo": payload.referenceNo, "file_link": ra_result.get("driveLink")}),
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                logger.info("Published RA GEM parsing job for %s", payload.referenceNo)
            else:
                logger.error("RA_GEM_DOWNLOAD failed for %s: %s", payload.referenceNo, ra_result.get("error"))

            ch.basic_ack(delivery_tag=method.delivery_tag)
        elif isinstance(payload, NonGemDownloadTask):
            reference_no = payload.referenceNo or payload.tenderId
            drive_folder_id = settings.GOOGLE_DRIVE_FOLDER_ID or None
            email = settings.TENDER247_EMAIL
            password = settings.TENDER247_PASSWORD
            if not email or not password:
                raise ValueError("TENDER247_EMAIL and TENDER247_PASSWORD must be configured")

            asyncio.set_event_loop(asyncio.new_event_loop())
            result = login_tender247(email, password, reference_no, drive_folder_id)

            if result.get("success"):
                drive = result.get("drive", {})
                tender_merged = TenderMerged.objects.filter(referenceno=reference_no).first()
                if tender_merged:
                    file_name = drive.get("name", "")
                    extension = Path(file_name).suffix if file_name else ""
                    TenderFiles.objects.create(
                        name=file_name,
                        extension=extension,
                        url=drive.get("webViewLink", ""),
                        source="tender247",
                        tags=["tenderDocument"],
                        tendermergedid=tender_merged,
                        createdat=timezone.now(),
                        updatedat=timezone.now(),
                    )
                    ch.basic_publish(
                        exchange="",
                        routing_key=settings.TENDER_PARSING_QUEUE,
                        body=json.dumps({
                            "type": "NON_GEM_BOQ_PARSING",
                            "referenceNo": reference_no,
                            "file_link": drive.get("webViewLink", ""),
                        }),
                        properties=pika.BasicProperties(delivery_mode=2),
                    )
                    logger.info("Published NON_GEM_BOQ_PARSING job for %s", reference_no)
                logger.info(f"[NON_GEM_DOWNLOAD] Result for {reference_no}: success={result.get('success')}")
            else:
                tiger_email = settings.TENDER_TIGER_EMAIL
                tiger_password = settings.TENDER_TIGER_PASSWORD
                tiger_result = login_tiger(tiger_email, tiger_password, reference_no, drive_folder_id)
                if tiger_result.get("success"):
                                drive = tiger_result.get("drive", {})
                                tender_merged = TenderMerged.objects.filter(referenceno=reference_no).first()
                                if tender_merged:
                                    file_name = drive.get("name", "")
                                    extension = Path(file_name).suffix if file_name else ""
                                    TenderFiles.objects.create(
                                        name=file_name,
                                        extension=extension,
                                        url=drive.get("webViewLink", ""),
                                        source="tendertiger",
                                        tags=["tenderDocument"],
                                        tendermergedid=tender_merged,
                                        createdat=timezone.now(),
                                        updatedat=timezone.now(),
                                    )
                                    ch.basic_publish(
                                        exchange="",
                                        routing_key=settings.TENDER_PARSING_QUEUE,
                                        body=json.dumps({
                                            "type": "NON_GEM_BOQ_PARSING",
                                            "referenceNo": reference_no,
                                            "file_link": drive.get("webViewLink", ""),
                                        }),
                                        properties=pika.BasicProperties(delivery_mode=2),
                                    )
                                    logger.info("Published NON_GEM_BOQ_PARSING job for %s", reference_no)
                                logger.info(f"[NON_GEM_DOWNLOAD] Result for {reference_no}: success={tiger_result.get('success')}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            logger.warning("Unknown message type: %s", payload.type)
            ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error("Failed to process message: %s", e)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


class Command(BaseCommand):
    help = "Consume messages from the tender:tasks RabbitMQ queue"

    def handle(self, *args, **options):
        queue = settings.TENDER_TASKS_QUEUE

        if not settings.RABBITMQ_URL:
            raise CommandError(
                "RABBITMQ_URL is not set. Please configure it in your environment."
            )

        self.stdout.write(f"Connecting to RabbitMQ, listening on queue: {queue}")
        self.stdout.write("Press Ctrl+C to stop")

        conn = None
        channel = None

        try:
            channel = get_channel(queue)
            conn = channel.connection
            ensure = get_channel(settings.TENDER_PARSING_QUEUE)
            ensure.connection.close()
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue, on_message_callback=callback)

            channel.start_consuming()
        except KeyboardInterrupt:
            self.stdout.write("\nShutting down consumer...")
            if channel:
                try:
                    channel.stop_consuming()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            self.stdout.write("Consumer stopped.")
        except Exception as e:
            raise CommandError(f"Consumer error: {e}")