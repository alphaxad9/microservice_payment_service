import os
import sys
import signal
import time
import logging
import json
import asyncio
from typing import Any, Dict, Optional

from dotenv import load_dotenv
load_dotenv()

# Django must be imported BEFORE calling django.setup()
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payment_service.settings")
django.setup()

from typing import Any, Dict, Optional
import pika
from typing import Callable, Awaitable, Any
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from django.core.cache import cache
 
from src.messaging.rabbitMQ.config import (
    RABBIT_USER,
    RABBIT_PORT,
    RABBIT_HOST,
    RABBIT_PASSWORD,
    RABBIT_VHOST,
    RABBIT_QUEUE,
)

logger = logging.getLogger(__name__)
_connection: Optional[pika.BlockingConnection] = None

HANDLER_REGISTRY: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}



def is_duplicate(message_id: str) -> bool:
    """Deduplication using Django cache (Redis/Memcached recommended)."""
    if not message_id or message_id == "unknown":
        return False
    key = f"outbox_processed:{message_id}"
    if cache.get(key):
        return True
    # Set with 7-day expiry
    cache.set(key, "1", timeout=7 * 24 * 3600)
    return False


async def process_domain_event(event_type: str, event_data: dict[str, Any]) -> None:
    handler = HANDLER_REGISTRY.get(event_type)
    if handler:
        await handler(event_data)
    else:
        logger.warning(f"⚠️ No handler registered for {event_type}")


def callback(
    ch: BlockingChannel,
    method: Basic.Deliver,
    properties: BasicProperties,
    body: bytes,
) -> None:
    """Process incoming messages (idempotent)."""
    message_id = properties.message_id or "unknown"

    # Deduplication
    if is_duplicate(message_id):
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("🔁 Duplicate message ignored", extra={"message_id": message_id})
        return

    try:
        event_data: Dict[str, Any] = json.loads(body.decode("utf-8"))
        event_type: str = (
            properties.headers.get("event_type", "unknown") if properties.headers else "unknown"
        )

        logger.info(
            "📬 EVENT RECEIVED",
            extra={
                "event_type": event_type,
                "message_id": message_id,
                "data": event_data,
            },
        )

        # Run async domain event processing
        asyncio.run(process_domain_event(event_type, event_data))

        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("✅ Event processed successfully", extra={"message_id": message_id})

    except Exception as e:
        logger.exception(
            "❌ Failed to process message",
            extra={"error": str(e), "message_id": message_id},
        )
        # Dead-letter queue
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        logger.warning("📤 Message sent to DLQ", extra={"message_id": message_id})


def create_connection() -> pika.BlockingConnection:
    """Create RabbitMQ connection."""
    credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )
    return pika.BlockingConnection(parameters)


def start_consumer() -> None:
    """Start the consumer loop."""
    global _connection
    while True:
        try:
            logger.info("🔌 Connecting to RabbitMQ...")
            _connection = create_connection()
            channel = _connection.channel()
            channel.queue_declare(queue=RABBIT_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=RABBIT_QUEUE, on_message_callback=callback)
            logger.info(f' [*] Waiting for messages on "{RABBIT_QUEUE}". Press CTRL+C to exit')
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection error: {e}. Retrying in 5s...")
            if _connection and not _connection.is_closed:
                _connection.close()
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("🛑 Consumer interrupted by user")
            break
        except Exception as e:
            logger.exception(f"Unexpected error in consumer: {e}")
            break

    if _connection and _connection.is_open:
        _connection.close()
    logger.info("✅ Consumer stopped.")


def signal_handler(sig, frame):
    logger.info("Received shutdown signal. Exiting gracefully...")
    if _connection and _connection.is_open:
        _connection.close()
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    start_consumer()
