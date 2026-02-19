from django.apps import AppConfig


class EventstoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.infrastructure.apps.eventstore'
