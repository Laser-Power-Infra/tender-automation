from django.conf import settings
import pika


def get_connection():
    url = settings.RABBITMQ_URL
    if not url:
        raise ValueError(
            "RABBITMQ_URL is not configured. Set the RABBITMQ_URL environment variable."
        )
    params = pika.URLParameters(url)
    return pika.BlockingConnection(params)


def get_channel(queue):
    conn = get_connection()
    channel = conn.channel()
    channel.queue_declare(queue=queue, durable=True)
    return channel
