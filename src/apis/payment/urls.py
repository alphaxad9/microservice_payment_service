# src/application/payment/urls.py

from django.urls import path
from .command_views import (
    create_deposit,
    create_withdrawal,
    create_booking_payment,
    create_refund,
    process_payment,
    succeed_payment,
    fail_payment,
    cancel_payment,
    mark_payment_as_refunded,
)
from .query_views import (
    get_payment,
    list_payments_by_user,
    list_payments_by_wallet,
    check_payment_exists,
)

app_name = "payment"

urlpatterns = [
    # ----------------------------
    # Command Endpoints (Write)
    # ----------------------------

    # Idempotent creation endpoints (require Idempotency-Key header)
    path("deposits/", create_deposit, name="create_deposit"),
    path("withdrawals/", create_withdrawal, name="create_withdrawal"),
    path("booking-payments/", create_booking_payment, name="create_booking_payment"),
    path("refunds/", create_refund, name="create_refund"),

    # State transition endpoints (POST with payment_id in body)
    path("process/", process_payment, name="process_payment"),
    path("succeed/", succeed_payment, name="succeed_payment"),
    path("fail/", fail_payment, name="fail_payment"),
    path("cancel/", cancel_payment, name="cancel_payment"),
    path("mark-as-refunded/", mark_payment_as_refunded, name="mark_as_refunded"),

    # ----------------------------
    # Query Endpoints (Read)
    # ----------------------------

    # Retrieve single payment (with owner data)
    path("payments/<uuid:payment_id>/", get_payment, name="get_payment"),

    # Existence check
    path("payments/exists/", check_payment_exists, name="check_payment_exists"),

    # User-scoped listings (with owner data)
    path("payments/by-user/", list_payments_by_user, name="list_payments_by_user"),
    path("payments/by-wallet/", list_payments_by_wallet, name="list_payments_by_wallet"),
]