# src/messaging/kafka/outbox_publisher.py

import json
import logging
import signal
import sys
import time
from typing import Any, Dict, List

from django.db import close_old_connections, transaction
from django.utils import timezone

from confluent_kafka import Producer

from src.infrastructure.apps.outbox.models import EventOutbox
from src.infrastructure.repos.outbox.orm_repository import DjangoOutBoxORMRepository
from src.messaging.kafka.config import KAFKA_BROKERS, KAFKA_TOPIC, KAFKA_RETRIES

logger = logging.getLogger(__name__)


def _truncate_payload(payload: Dict[str, Any], max_length: int = 500) -> str:
    """Truncate large payloads for logging to avoid flooding logs"""
    payload_str = json.dumps(payload, ensure_ascii=False)
    if len(payload_str) > max_length:
        return payload_str[: max_length - 3] + "..."
    return payload_str


class OutboxKafkaPublisher:
    """
    Generic Kafka Outbox Publisher
    Publishes domain events from EventOutbox to Kafka.
    Uses short-lived transactions to safely claim events without long DB locks.
    """

    def __init__(self):
        self.outbox_repo = DjangoOutBoxORMRepository()
        self.producer = None
        self._create_producer()

    def _create_producer(self):
        conf = {
            'bootstrap.servers': KAFKA_BROKERS,
            'enable.idempotence': True,
            'acks': 'all',
            'retries': 2147483647,  # Max int; relies on idempotence
            'max.in.flight.requests.per.connection': 5,
        }
        self.producer = Producer(conf)
        logger.info("Kafka producer created with idempotence enabled")

    def _delivery_report(self, err, msg, event_id: str, event_type: str, payload_preview: str):
        """Delivery callback — called once per message"""
        if err is not None:
            error_msg = err.str()
            logger.error(
                f"Kafka delivery FAILED for event {event_id} ({event_type}): {error_msg}"
            )
            self.outbox_repo.mark_as_failed(event_id, error_msg)

            # Mark as dead after max retries
            try:
                event = EventOutbox.objects.get(id=event_id)
                if event.retry_count >= KAFKA_RETRIES:
                    EventOutbox.objects.filter(id=event_id).update(processed_at=timezone.now())
                    logger.critical(f"Max retries reached — event {event_id} marked as dead")
            except EventOutbox.DoesNotExist:
                pass
        else:
            logger.info(
                f"Kafka published: {event_type} (id={event_id}) payload={payload_preview}"
            )
            self.outbox_repo.mark_as_published(event_id)

    def publish_events(self):
        # 🔑 CRITICAL: get_unpublished_events() MUST use transaction.atomic() internally
        # when calling .select_for_update(). See repository example below.
        events = self.outbox_repo.get_unpublished_events(limit=20)
        if not events:
            return

        for event in events:
            try:
                payload_bytes = json.dumps(event.event_payload).encode("utf-8")
                payload_preview = _truncate_payload(event.event_payload)
                headers = [("event_type", event.event_type.encode("utf-8"))]
                key = str(event.id).encode("utf-8")

                self.producer.produce(
                    topic=KAFKA_TOPIC,
                    key=key,
                    value=payload_bytes,
                    headers=headers,
                    on_delivery=lambda e, m, eid=event.id, et=event.event_type, pp=payload_preview:
                        self._delivery_report(e, m, eid, et, pp),
                )

            except BufferError:
                logger.warning("Producer buffer full — flushing before retry")
                self.producer.flush(timeout=10.0)
                # Retry once
                self.producer.produce(
                    topic=KAFKA_TOPIC,
                    key=key,
                    value=payload_bytes,
                    headers=headers,
                    on_delivery=lambda e, m, eid=event.id, et=event.event_type, pp=payload_preview:
                        self._delivery_report(e, m, eid, et, pp),
                )
            except Exception as e:
                logger.error(f"Failed to queue event {event.id} ({event.event_type}): {e}")
                self.outbox_repo.mark_as_failed(event.id, str(e))

        remaining = self.producer.flush(timeout=10.0)
        if remaining > 0:
            logger.warning(f"{remaining} messages still pending delivery after flush")

    def start(self, interval: int = 3):
        logger.info("Kafka Outbox Publisher Started (publishing ALL domain events)")
        while True:
            close_old_connections()
            try:
                self.publish_events()
            except Exception as e:
                logger.exception(f"Unexpected error in publisher loop: {e}")
                self.producer = None
                time.sleep(5)
                self._create_producer()
            time.sleep(interval)


def shutdown(sig, frame):
    logger.info("Shutdown signal received.")
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    OutboxKafkaPublisher().start()