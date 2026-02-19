# admin.py
from django.contrib import admin
from .models import EventStore, ProjectionState


@admin.register(EventStore)
class EventStoreAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'aggregate_id',
        'aggregate_type',
        'aggregate_version',
        'event_type',
        'created_at',
    )
    list_filter = (
        'aggregate_type',
        'event_type',
        'created_at',
    )
    search_fields = (
        'aggregate_id',
        'aggregate_type',
        'event_type',
    )
    readonly_fields = (
        'id',
        'aggregate_id',
        'aggregate_type',
        'aggregate_version',
        'event_type',
        'event_payload',
        'metadata',
        'created_at',
    )
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        # Prevent adding events through admin (append-only via domain logic)
        return False

    def has_change_permission(self, request, obj=None):
        # Prevent editing existing events
        return False

    def has_delete_permission(self, request, obj=None):
        # Optionally allow deletion (set to False if you want full immutability)
        return False


@admin.register(ProjectionState)
class ProjectionStateAdmin(admin.ModelAdmin):
    list_display = (
        'projection_name',
        'version',
        'last_event_id',
        'updated_at',
    )
    readonly_fields = (
        'projection_name',
        'version',
        'last_event_id',
        'updated_at',
    )
    search_fields = ('projection_name',)
    ordering = ('projection_name',)

    def has_add_permission(self, request):
        # Typically managed programmatically, not manually via admin
        return False

    def has_delete_permission(self, request, obj=None):
        # Prevent accidental deletion
        return False