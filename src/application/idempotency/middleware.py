from django.http import HttpResponse
from asgiref.sync import async_to_sync
import uuid

class IdempotencyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only apply idempotency rules to specific creation endpoints
        IDEMPOTENT_PATHS = {
            "/payment_service/payments/deposits/",
            "/payment_service/payments/withdrawals/",
            "/payment_service/payments/booking-payments/",   # or whatever exact path you use
            "/payment_service/payments/refunds/",            # if you have it
            # Add more creation endpoints here in the future
        }

        # Skip entirely if:
        # - Not a mutating method
        # - Not one of the protected paths
        # - Test/debug endpoints
        if (
            request.method not in ("POST", "PUT", "PATCH")
            or request.path not in IDEMPOTENT_PATHS
            or request.path.startswith("/payment_service/idempotency/test/")
        ):
            return self.get_response(request)

        # At this point: it's a protected creation endpoint → enforce header
        idempotency_key = request.headers.get("Idempotency-Key")

        if not idempotency_key:
            return HttpResponse(
                content="Missing Idempotency-Key header for this endpoint",
                status=400,
                content_type="text/plain"
            )

        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            return HttpResponse(
                content="Idempotency-Key must be a valid UUID",
                status=400,
                content_type="text/plain"
            )

        # Optional: you could add early basic validation (length, etc.)
        # But for now this is enough

        return self.get_response(request)