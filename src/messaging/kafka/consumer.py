import os
import sys
import signal
import json
import logging
import asyncio
from typing import Any, Dict, Callable, Awaitable
from confluent_kafka import Consumer, KafkaException

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payment_service.settings")
django.setup()
from src.messaging.kafka.dispatchers.payment.dispatchers import PAYMENT_EVENT_HANDLERS
from django.core.cache import cache
from src.messaging.kafka.config import (
    KAFKA_BROKERS,
    KAFKA_TOPIC,
    KAFKA_GROUP_ID,
    KAFKA_AUTO_OFFSET_RESET,
    KAFKA_POLL_TIMEOUT,
)

logger = logging.getLogger("kafka.consumer")

HANDLER_REGISTRY: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}
HANDLER_REGISTRY.update(PAYMENT_EVENT_HANDLERS)

def is_duplicate(message_id: str) -> bool:
    if not message_id or message_id == "unknown":
        return False
    key = f"kafka_processed:{message_id}"
    if cache.get(key):
        return True
    cache.set(key, "1", timeout=7 * 24 * 3600)
    return False

async def process_event(event_type: str, data: dict):
    handler = HANDLER_REGISTRY.get(event_type)
    if handler:
        await handler(data)
    else:
        logger.warning(f"⚠️ No handler registered for {event_type}")

class KafkaDomainConsumer:
    def __init__(self):
        self.consumer = Consumer({
            "bootstrap.servers": KAFKA_BROKERS,
            "group.id": KAFKA_GROUP_ID,
            "auto.offset.reset": KAFKA_AUTO_OFFSET_RESET,
            "enable.auto.commit": False,
            "isolation.level": "read_committed",
        })
        self.consumer.subscribe([KAFKA_TOPIC])
        logger.info(f"✅ Subscribed to Kafka topic: {KAFKA_TOPIC}")

    def start(self):
        logger.info("🚀 Starting Kafka consumer loop...")
        try:
            while True:
                msg = self.consumer.poll(timeout=KAFKA_POLL_TIMEOUT)
                if msg is None:
                    continue
                if msg.error():
                    raise KafkaException(msg.error())

                # Parse headers safely
                headers = {}
                for k, v in (msg.headers() or []):
                    key = k.decode("utf-8") if isinstance(k, bytes) else k
                    value = v.decode("utf-8") if isinstance(v, bytes) else v
                    headers[key] = value

                event_type = headers.get("event_type", "unknown")
                message_id = msg.key().decode("utf-8") if msg.key() else "unknown"

                if is_duplicate(message_id):
                    logger.info(f"🔁 Duplicate skipped: {message_id}")
                    # Still commit to advance offset
                    self.consumer.commit(msg, asynchronous=False)
                    continue

                raw_value = msg.value().decode("utf-8") if msg.value() else ""
                try:
                    payload = json.loads(raw_value)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Non-JSON message (event_type={event_type})")
                    payload = {"raw_value": raw_value}

                try:
                    # Use asyncio.run() — safe in sync context
                    asyncio.run(process_event(event_type, payload))
                    logger.info(f"✅ Processed: {event_type}")
                    self.consumer.commit(msg, asynchronous=False)
                except Exception as e:
                    logger.exception(f"💥 Failed to process {event_type}: {e}")
                    # Do NOT commit — retry on next poll

        except KeyboardInterrupt:
            logger.info("🛑 Stopped by user.")
        except Exception as e:
            logger.critical("Fatal error: %s", e, exc_info=True)
        finally:
            self.consumer.close()
            logger.info("🔌 Consumer closed.")

def signal_handler(sig, frame):
    logger.info("Shutdown signal received.")
    sys.exit(0)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.info("✅ Starting Kafka consumer...")
    KafkaDomainConsumer().start()