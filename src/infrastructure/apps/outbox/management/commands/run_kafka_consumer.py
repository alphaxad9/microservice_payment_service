import logging
from django.core.management.base import BaseCommand
from src.messaging.kafka.consumer import KafkaDomainConsumer


class Command(BaseCommand):
    help = "Run Kafka consumer to process domain events"

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO)
        self.stdout.write(self.style.SUCCESS("✅ Starting Kafka consumer..."))
        KafkaDomainConsumer().start()



# python manage.py run_kafka_consumer
