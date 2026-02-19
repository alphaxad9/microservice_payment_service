# src/messaging/kafka/producer.py

import json
import logging
from datetime import datetime, date
from uuid import UUID
from enum import Enum
from decimal import Decimal
from confluent_kafka import Producer

from .config import KAFKA_BROKERS, KAFKA_TOPIC

logger = logging.getLogger(__name__)

producer = Producer({"bootstrap.servers": KAFKA_BROKERS})


def json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, UUID):
        return str(obj)

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, Decimal):
        return float(obj)

    raise TypeError(f"Type {type(obj)} not serializable")


def publish_to_kafka(event_type: str, payload: dict, key: str | None = None):
    try:
        value = json.dumps(payload, default=json_serializer).encode("utf-8")

        producer.produce(
            KAFKA_TOPIC,
            key=key.encode("utf-8") if key else None,
            value=value,
            headers=[("event_type", event_type.encode("utf-8"))],
        )

        producer.flush()
        logger.info("📨 Sent Kafka event: %s", event_type)

    except Exception as e:
        logger.error("🔥 Kafka publish failed: %s", e, exc_info=True)
        raise