from django.core.management.base import BaseCommand
from src.messaging.kafka.outbox_publisher import OutboxKafkaPublisher

class Command(BaseCommand):
    help = "Run Kafka outbox publisher loop"

    def handle(self, *args, **options):
        publisher = OutboxKafkaPublisher()
        publisher.start()


# python manage.py run_kafka_publisher
