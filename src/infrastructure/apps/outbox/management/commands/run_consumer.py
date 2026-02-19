# src/infrastructure/management/commands/run_consumer.py
from django.core.management.base import BaseCommand
from src.messaging.rabbitMQ.consumer import start_consumer


class Command(BaseCommand):
    help = "Run the RabbitMQ consumer to process incoming events."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("✅ Starting RabbitMQ consumer..."))
        self.stdout.write(
            self.style.WARNING(
                "ℹ️  Event handlers are already wired via AppConfig.ready()."
            )
        )
        start_consumer()