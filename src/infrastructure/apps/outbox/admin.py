# apps/events/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta
from src.infrastructure.apps.outbox.models import EventOutbox


@admin.register(EventOutbox)
class EventOutboxAdmin(admin.ModelAdmin):
    # === Display ===
    list_display = (
        'status_indicator',
        'event_type',
        'aggregate_type',
        'aggregate_id_short',
        'created_at',
        'aggregate_version',  
        'published_at',
        'retry_count_display',
        'trace_id_short',
    )
    
    list_filter = (
        ('processed_at', admin.EmptyFieldListFilter),  # Unprocessed vs processed
        'aggregate_type',
        'event_type',
        'retry_count',
        'created_at',
        'aggregate_version',
    )
    
    search_fields = (
        'event_type',
        'aggregate_id',
        'trace_id',
        'event_payload',  # JSON search (PostgreSQL supports this well)
    )
    
    readonly_fields = (
    'id',
    'created_at',
    'published_at',
     'aggregate_version',
    'processed_at',
    'payload_pretty',
    'metadata_pretty',
    'error_message',
    'retry_count',
    'status_indicator',   # ✅ add here
    )


    
    fieldsets = (
        ('Event Identity', {
            'fields': ('id', 'event_type')
        }),
        ('Aggregate Context', {
            'fields': ('aggregate_type', 'aggregate_id')
        }),
        ('Payload & Metadata', {
            'fields': ('payload_pretty', 'metadata_pretty')
        }),
        ('Delivery Status', {
            'fields': ('status_indicator', 'created_at', 'published_at', 'processed_at', 'retry_count')
        }),
        ('Observability', {
            'fields': ('trace_id',)
        }),
        ('Failure Handling', {
            'fields': ('error_message',),
            'classes': ('collapse',)  # Hidden by default
        }),
    )

    # === Custom Display Methods ===
    def status_indicator(self, obj):
        if obj.processed_at:
            return format_html('<span style="color: green;">✅ Published</span>')
        elif obj.retry_count > 0:
            return format_html('<span style="color: orange;">⚠️ Retrying ({})</span>', obj.retry_count)
        else:
            return format_html('<span style="color: gray;">⏳ Pending</span>')
    status_indicator.short_description = "Status"
    status_indicator.admin_order_field = 'processed_at'

    def aggregate_id_short(self, obj):
        return str(obj.aggregate_id)[:8]
    aggregate_id_short.short_description = "Aggregate ID (short)"

    def trace_id_short(self, obj):
        return str(obj.trace_id)[:8] if obj.trace_id else "—"
    trace_id_short.short_description = "Trace ID (short)"

    def retry_count_display(self, obj):
        if obj.retry_count == 0:
            return "—"
        return obj.retry_count
    retry_count_display.short_description = "Retries"

    def payload_pretty(self, obj):
        import json
        try:
            pretty = json.dumps(obj.event_payload, indent=2, ensure_ascii=False)
            return format_html('<pre style="white-space: pre-wrap; max-width: 800px;">{}</pre>', pretty)
        except Exception:
            return str(obj.event_payload)
    payload_pretty.short_description = "Event Payload (Formatted)"

    def metadata_pretty(self, obj):
        import json
        try:
            pretty = json.dumps(obj.metadata, indent=2, ensure_ascii=False)
            return format_html('<pre style="white-space: pre-wrap; max-width: 800px;">{}</pre>', pretty)
        except Exception:
            return str(obj.metadata)
    metadata_pretty.short_description = "Metadata (Formatted)"

    # === Performance & Safety ===
    list_select_related = False  # No FKs, so not needed
    show_full_result_count = False  # Avoid slow COUNT(*) on large tables
    list_per_page = 50

    # === Actions ===
    actions = ['mark_as_unprocessed', 'delete_processed_old']

    @admin.action(description="Mark selected events as UNPROCESSED (for replay)")
    def mark_as_unprocessed(self, request, queryset):
        updated = queryset.update(
            processed_at=None,
            published_at=None,
            retry_count=0,
            error_message=None
        )
        self.message_user(request, f"{updated} events marked for republishing.")

    @admin.action(description="Delete PROCESSED events older than 7 days")
    def delete_processed_old(self, request, queryset):
        cutoff = timezone.now() - timedelta(days=7)
        old_processed = EventOutbox.objects.filter(
            processed_at__isnull=False,
            created_at__lt=cutoff
        )
        count, _ = old_processed.delete()
        self.message_user(request, f"{count} old processed events deleted.")

    # Prevent accidental mass deletion
    def has_delete_permission(self, request, obj=None):
        # Allow deletion only via the custom action (not the delete button)
        return False

    def has_add_permission(self, request):
        # Outbox entries should only be created by domain logic, not manually
        return False