# src/messaging/kafka/command_publisher.py

import logging
from uuid import UUID
from src.messaging.kafka.producer import publish_to_kafka
from typing import Dict, Any
logger = logging.getLogger(__name__)

class KafkaCommandPublisher:
    """
    Publishes integration commands to Kafka.
    Uses prefix 'command.' to distinguish from events.
    """

    def publish(self, command_name: str, payload: Dict[str, Any], key: str | UUID | None = None):
        """
        :param command_name: e.g. "RequestPaymentForBooking"
        :param payload: dict from command.model_dump()
        :param key: usually booking_id as str for partitioning
        """
        event_type = f"command.{command_name}"

        publish_to_kafka(
            event_type=event_type,
            payload=payload,
            key=str(key) if key else None,
        )

        logger.info(
            "Published command %s to Kafka (key=%s)",
            command_name,
            key,
        )