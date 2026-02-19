# src/application/idempotency/urls.py

from django.urls import path
from .command_views import (
    create_test_idempotency_key,
    begin_test_processing,
    record_test_failure,
    cleanup_expired_keys_view,
)
from .query_views import (
    get_idempotency_key_view,
    list_user_idempotency_keys_view,
    list_keys_by_status_view,
    list_expired_keys_view,
    count_user_keys_view,
    get_idempotency_metrics_view,
)

app_name = "idempotency"

urlpatterns = [
    # === Command/Test Endpoints (for simulation & testing) ===
    path("test/create/", create_test_idempotency_key, name="create_test_key"),
    path("test/begin/", begin_test_processing, name="begin_test_processing"),
    path("test/failure/", record_test_failure, name="record_test_failure"),
    path("test/cleanup/", cleanup_expired_keys_view, name="cleanup_expired_keys"),

    # === Query Endpoints (read-only inspection & monitoring) ===
    path("keys/", get_idempotency_key_view, name="get_key"),  # uses ?key=...
    path("keys/user/", list_user_idempotency_keys_view, name="list_user_keys"),
    path("keys/status/", list_keys_by_status_view, name="list_keys_by_status"),
    path("keys/expired/", list_expired_keys_view, name="list_expired_keys"),
    path("keys/count/", count_user_keys_view, name="count_user_keys"),
    path("metrics/", get_idempotency_metrics_view, name="get_metrics"),
]