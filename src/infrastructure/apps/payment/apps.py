# src/infrastructure/apps/payment/apps.py

from django.apps import AppConfig


class PaymentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.infrastructure.apps.payment'

    def ready(self) -> None:
        # Register projection runner using the global registry
        from src.infrastructure.projectors.payment.projector import PaymentProjectionRunner
        from src.infrastructure.projectors.registry import register_payment_projection

        register_payment_projection("payment", PaymentProjectionRunner())

        # Configure payment event handlers on the global event bus
        from src.messaging.payment.config import configure_payment_event_bus

        configure_payment_event_bus()