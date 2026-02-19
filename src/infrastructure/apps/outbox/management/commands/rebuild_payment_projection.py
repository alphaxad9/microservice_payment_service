# src/infrastructure/apps/payment/management/commands/rebuild_payment_projection.py

from django.core.management.base import BaseCommand
from django.db import transaction
from src.infrastructure.apps.eventstore.models import ProjectionState, EventStore
from src.infrastructure.apps.payment.models import PaymentReadModel
from src.infrastructure.projectors.payment.projector import PaymentProjectionRunner
from src.domain.apps.payment.events import event_from_dict


class Command(BaseCommand):
    help = "Rebuilds the payment read model projection from scratch."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING("⚠️  Disabling projection and deleting existing read models...")
        )

        # Get or create the projection state, then set version to 0 (disabled)
        state, created = ProjectionState.objects.get_or_create(
            projection_name="payment",
            defaults={"version": 0}
        )
        state.version = 0
        state.last_event_id = None
        state.save(update_fields=["version", "last_event_id"])

        # Clear read model
        deleted_count, _ = PaymentReadModel.objects.all().delete()
        self.stdout.write(f"🗑️  Deleted {deleted_count} PaymentReadModel records.")

        runner = PaymentProjectionRunner()
        last_event_id = None
        count = 0

        # Process all Payment events in order
        events = EventStore.objects.filter(
            aggregate_type="Payment"
        ).order_by("created_at")

        total = events.count()
        self.stdout.write(f"🔁 Replaying {total} events...")

        for record in events:
            try:
                event = event_from_dict(
                    event_type=record.event_type,
                    event_payload=record.event_payload,
                )
                runner.projector.project(event)
                last_event_id = record.id
                count += 1
                if count % 100 == 0:
                    self.stdout.write(f"  → Processed {count}/{total} events...")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"❌ Failed to project event {record.id} ({record.event_type}): {e}"
                    )
                )
                raise

        # Re-enable projection with correct version and last event ID
        state.version = PaymentProjectionRunner.VERSION
        state.last_event_id = last_event_id
        state.save(update_fields=["version", "last_event_id"])

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Payment projection rebuilt successfully! ({count} events processed)"
            )
        )



#python manage.py rebuild_payment_projection