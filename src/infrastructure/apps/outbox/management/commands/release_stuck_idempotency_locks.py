from django.utils import timezone
from django.core.management.base import BaseCommand
from src.infrastructure.apps.idempontence.models import IdempotencyKey as IdempotencyKeyModel
from src.domain.idempotency.models import IdempotencyStatus

class Command(BaseCommand):
    help = 'Release stuck locks on pending idempotency keys'

    def handle(self, *args, **options):
        now = timezone.now()
        stuck_count = IdempotencyKeyModel.objects.filter(
            locked_until__lt=now,
            status=IdempotencyStatus.PENDING.name
        ).update(locked_until=None, locked_by=None)
        self.stdout.write(self.style.SUCCESS(f'Released {stuck_count} stuck locks'))



#python manage.py release_stuck_idempotency_locks