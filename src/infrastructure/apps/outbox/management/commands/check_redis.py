# src/infrastructure/management/commands/check_redis.py
from django.core.management.base import BaseCommand
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class Command(BaseCommand):
    help = "Check Redis channel layer connectivity"

    def handle(self, *args, **kwargs):
        layer = get_channel_layer()
        async_to_sync(layer.send)("test_channel", {"type": "test.message", "text": "Hello Redis!"})
        self.stdout.write(self.style.SUCCESS("Redis channel layer is working"))





# python manage.py check_redis


# Start 2 separate Django ASGI workers
# daphne -b 0.0.0.0 -p 8000 src.infrastructure.asgi:application
# daphne -b 0.0.0.0 -p 8001 src.infrastructure.asgi:application
