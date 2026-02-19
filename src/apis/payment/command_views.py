# src/application/payment/views/payment_command_views.py

import json
import logging
from decimal import Decimal
from uuid import UUID
from typing import Optional
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from dataclasses import asdict

from src.application.payment.factory import get_payment_command_handler
from src.domain.apps.payment.exceptions import PaymentDomainError, PaymentNotFoundError
from src.domain.idempotency.exceptions import (
    IdempotencyKeyAlreadyExistsError,
    IdempotencyKeyReuseWithDifferentPayloadError,
)

logger = logging.getLogger(__name__)


def _payment_view_to_dict(payment_view) -> dict:
    if hasattr(payment_view, "to_dict"):
        return payment_view.to_dict()
    return asdict(payment_view)


@csrf_exempt
async def create_deposit(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not hasattr(request, "user_id") or not request.user_id:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return JsonResponse({"error": "Missing Idempotency-Key header"}, status=400)

    wallet_id_str = body.get("wallet_id")
    if not wallet_id_str:
        return JsonResponse({"error": "Missing required field: wallet_id"}, status=400)

    amount_str = body.get("amount")
    if amount_str is None:
        return JsonResponse({"error": "Missing required field: amount"}, status=400)

    currency = body.get("currency")
    if not currency:
        return JsonResponse({"error": "Missing required field: currency"}, status=400)

    payment_method = body.get("payment_method")
    if not payment_method:
        return JsonResponse({"error": "Missing required field: payment_method"}, status=400)

    try:
        wallet_id = UUID(wallet_id_str)
        user_id = UUID(request.user_id)
        amount = Decimal(str(amount_str))
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": f"Invalid input format: {str(e)}"}, status=400)

    reference_id = body.get("reference_id")
    if reference_id:
        try:
            reference_id = UUID(reference_id)
        except ValueError:
            return JsonResponse({"error": "Invalid reference_id UUID format"}, status=400)

    description = body.get("description")
    payment_id_str = body.get("payment_id")
    payment_id = UUID(payment_id_str) if payment_id_str else None

    try:
        payment_view = await get_payment_command_handler().create_deposit(
            idempotency_key=idempotency_key,
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            reference_id=reference_id,
            description=description,
            payment_id=payment_id,
        )
    except (IdempotencyKeyAlreadyExistsError, IdempotencyKeyReuseWithDifferentPayloadError) as e:
        # These are handled internally by the executor; should not reach here
        logger.warning(f"Unexpected idempotency error: {e}")
        return JsonResponse({"error": "Idempotency conflict"}, status=409)
    except PaymentDomainError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("Create deposit failed with traceback")
        # Print full traceback to console
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "error": "Internal server error",
            "detail": str(e)  # ← This will show the real cause
        }, status=500)

    return JsonResponse(_payment_view_to_dict(payment_view), status=201)


@csrf_exempt
async def create_withdrawal(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not hasattr(request, "user_id") or not request.user_id:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return JsonResponse({"error": "Missing Idempotency-Key header"}, status=400)

    wallet_id_str = body.get("wallet_id")
    if not wallet_id_str:
        return JsonResponse({"error": "Missing required field: wallet_id"}, status=400)

    amount_str = body.get("amount")
    if amount_str is None:
        return JsonResponse({"error": "Missing required field: amount"}, status=400)

    currency = body.get("currency")
    if not currency:
        return JsonResponse({"error": "Missing required field: currency"}, status=400)

    payment_method = body.get("payment_method")
    if not payment_method:
        return JsonResponse({"error": "Missing required field: payment_method"}, status=400)

    try:
        wallet_id = UUID(wallet_id_str)
        user_id = UUID(request.user_id)
        amount = Decimal(str(amount_str))
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": f"Invalid input format: {str(e)}"}, status=400)

    reference_id = body.get("reference_id")
    if reference_id:
        try:
            reference_id = UUID(reference_id)
        except ValueError:
            return JsonResponse({"error": "Invalid reference_id UUID format"}, status=400)

    description = body.get("description")
    payment_id_str = body.get("payment_id")
    payment_id = UUID(payment_id_str) if payment_id_str else None

    try:
        payment_view = await get_payment_command_handler().create_withdrawal(
            idempotency_key=idempotency_key,
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            reference_id=reference_id,
            description=description,
            payment_id=payment_id,
        )
    except PaymentDomainError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception:
        logger.exception("Create withdrawal failed")
        return JsonResponse({"error": "Failed to create withdrawal"}, status=500)

    return JsonResponse(_payment_view_to_dict(payment_view), status=201)


@csrf_exempt
async def create_booking_payment(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not hasattr(request, "user_id") or not request.user_id:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return JsonResponse({"error": "Missing Idempotency-Key header"}, status=400)

    wallet_id_str = body.get("wallet_id")
    booking_id_str = body.get("booking_id")
    amount_str = body.get("amount")
    currency = body.get("currency")
    payment_method = body.get("payment_method")

    missing_fields = []
    if not wallet_id_str:
        missing_fields.append("wallet_id")
    if not booking_id_str:
        missing_fields.append("booking_id")
    if amount_str is None:
        missing_fields.append("amount")
    if not currency:
        missing_fields.append("currency")
    if not payment_method:
        missing_fields.append("payment_method")

    if missing_fields:
        return JsonResponse({"error": f"Missing required fields: {', '.join(missing_fields)}"}, status=400)

    try:
        wallet_id = UUID(wallet_id_str)
        booking_id = UUID(booking_id_str)
        user_id = UUID(request.user_id)
        amount = Decimal(str(amount_str))
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": f"Invalid input format: {str(e)}"}, status=400)

    description = body.get("description")
    payment_id_str = body.get("payment_id")
    payment_id = UUID(payment_id_str) if payment_id_str else None

    try:
        payment_view = await get_payment_command_handler().create_payment_for_booking(
            idempotency_key=idempotency_key,
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            booking_id=booking_id,
            description=description,
            payment_id=payment_id,
        )
    except PaymentDomainError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception:
        logger.exception("Create booking payment failed")
        return JsonResponse({"error": "Failed to create booking payment"}, status=500)

    return JsonResponse(_payment_view_to_dict(payment_view), status=201)


@csrf_exempt
async def create_refund(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not hasattr(request, "user_id") or not request.user_id:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return JsonResponse({"error": "Missing Idempotency-Key header"}, status=400)

    wallet_id_str = body.get("wallet_id")
    original_payment_id_str = body.get("original_payment_id")
    amount_str = body.get("amount")
    currency = body.get("currency")

    missing_fields = []
    if not wallet_id_str:
        missing_fields.append("wallet_id")
    if not original_payment_id_str:
        missing_fields.append("original_payment_id")
    if amount_str is None:
        missing_fields.append("amount")
    if not currency:
        missing_fields.append("currency")

    if missing_fields:
        return JsonResponse({"error": f"Missing required fields: {', '.join(missing_fields)}"}, status=400)

    try:
        wallet_id = UUID(wallet_id_str)
        original_payment_id = UUID(original_payment_id_str)
        user_id = UUID(request.user_id)
        amount = Decimal(str(amount_str))
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": f"Invalid input format: {str(e)}"}, status=400)

    refund_id_str = body.get("refund_id")
    refund_id = UUID(refund_id_str) if refund_id_str else None
    description = body.get("description")

    try:
        payment_view = await get_payment_command_handler().create_refund(
            idempotency_key=idempotency_key,
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            original_payment_id=original_payment_id,
            refund_id=refund_id,
            description=description,
        )
    except PaymentDomainError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception:
        logger.exception("Create refund failed")
        return JsonResponse({"error": "Failed to create refund"}, status=500)

    return JsonResponse(_payment_view_to_dict(payment_view), status=201)



























# Helper to create consistent JSON error responses
def error_response(message: str, status: int, details: dict | None = None) -> JsonResponse:
    response_data = {"error": message}
    if details:
        response_data["details"] = details
    response = JsonResponse(response_data, status=status)
    response['Content-Type'] = 'application/json'
    return response


@csrf_exempt
async def process_payment(request):
    if request.method != "POST":
        return error_response("Method not allowed", 405)

    if not hasattr(request, "user_id") or not request.user_id:
        return error_response("Authentication required", 401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError as e:
        return error_response("Invalid JSON body", 400, {"detail": str(e)})

    payment_id_str = body.get("payment_id")
    if not payment_id_str:
        return error_response("Missing required field: payment_id", 400)

    try:
        payment_id = UUID(payment_id_str)
        await get_payment_command_handler().process_payment(payment_id)
        return JsonResponse({"message": "Payment processing initiated"}, status=202)
    except PaymentNotFoundError:
        return error_response("Payment not found", 404, {"payment_id": payment_id_str})
    except PaymentDomainError as e:
        return error_response("Payment domain error", 400, {"detail": str(e)})
    except ValueError as e:
        return error_response("Invalid payment_id UUID format", 400, {"detail": str(e), "received": payment_id_str})
    except Exception as exc:
        logger.exception("Process payment failed for payment_id: %s", payment_id_str)
        return error_response("Failed to process payment", 500, {"detail": str(exc)})


@csrf_exempt
async def succeed_payment(request):
    if request.method != "POST":
        return error_response("Method not allowed", 405)

    if not hasattr(request, "user_id") or not request.user_id:
        return error_response("Authentication required", 401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError as e:
        return error_response("Invalid JSON body", 400, {"detail": str(e)})

    payment_id_str = body.get("payment_id")
    if not payment_id_str:
        return error_response("Missing required field: payment_id", 400)

    try:
        payment_id = UUID(payment_id_str)
        await get_payment_command_handler().succeed_payment(payment_id)
        return JsonResponse({"message": "Payment succeeded"}, status=200)
    except PaymentNotFoundError:
        return error_response("Payment not found", 404, {"payment_id": payment_id_str})
    except PaymentDomainError as e:
        return error_response("Payment domain error", 400, {"detail": str(e)})
    except ValueError as e:
        return error_response("Invalid payment_id UUID format", 400, {"detail": str(e), "received": payment_id_str})
    except Exception as exc:
        logger.exception("Succeed payment failed for payment_id: %s", payment_id_str)
        return error_response("Failed to succeed payment", 500, {"detail": str(exc)})


@csrf_exempt
async def fail_payment(request):
    if request.method != "POST":
        return error_response("Method not allowed", 405)

    if not hasattr(request, "user_id") or not request.user_id:
        return error_response("Authentication required", 401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError as e:
        return error_response("Invalid JSON body", 400, {"detail": str(e)})

    payment_id_str = body.get("payment_id")
    reason = body.get("reason")  # reason can be empty string, but field is required

    if not payment_id_str:
        return error_response("Missing required field: payment_id", 400)

    try:
        payment_id = UUID(payment_id_str)
        await get_payment_command_handler().fail_payment(payment_id, reason)
        return JsonResponse({"message": "Payment failed"}, status=200)
    except PaymentNotFoundError:
        return error_response("Payment not found", 404, {"payment_id": payment_id_str})
    except PaymentDomainError as e:
        return error_response("Payment domain error", 400, {"detail": str(e)})
    except ValueError as e:
        return error_response("Invalid payment_id UUID format", 400, {"detail": str(e), "received": payment_id_str})
    except Exception as exc:
        logger.exception("Fail payment failed for payment_id: %s", payment_id_str)
        return error_response("Failed to fail payment", 500, {"detail": str(exc)})


@csrf_exempt
async def cancel_payment(request):
    if request.method != "POST":
        return error_response("Method not allowed", 405)

    if not hasattr(request, "user_id") or not request.user_id:
        return error_response("Authentication required", 401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError as e:
        return error_response("Invalid JSON body", 400, {"detail": str(e)})

    payment_id_str = body.get("payment_id")
    if not payment_id_str:
        return error_response("Missing required field: payment_id", 400)

    try:
        payment_id = UUID(payment_id_str)
        await get_payment_command_handler().cancel_payment(payment_id)
        return JsonResponse({"message": "Payment canceled"}, status=200)
    except PaymentNotFoundError:
        return error_response("Payment not found", 404, {"payment_id": payment_id_str})
    except PaymentDomainError as e:
        return error_response("Payment domain error", 400, {"detail": str(e)})
    except ValueError as e:
        return error_response("Invalid payment_id UUID format", 400, {"detail": str(e), "received": payment_id_str})
    except Exception as exc:
        logger.exception("Cancel payment failed for payment_id: %s", payment_id_str)
        return error_response("Failed to cancel payment", 500, {"detail": str(exc)})


@csrf_exempt
async def mark_payment_as_refunded(request):
    if request.method != "POST":
        return error_response("Method not allowed", 405)

    if not hasattr(request, "user_id") or not request.user_id:
        return error_response("Authentication required", 401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError as e:
        return error_response("Invalid JSON body", 400, {"detail": str(e)})

    payment_id_str = body.get("payment_id")
    refund_id_str = body.get("refund_id")

    if not payment_id_str or not refund_id_str:
        return error_response("Missing required fields: payment_id, refund_id", 400)

    try:
        payment_id = UUID(payment_id_str)
        refund_id = UUID(refund_id_str)
        await get_payment_command_handler().mark_payment_as_refunded(payment_id, refund_id)
        return JsonResponse({"message": "Payment marked as refunded"}, status=200)
    except PaymentNotFoundError:
        return error_response("Payment not found", 404, {"payment_id": payment_id_str})
    except PaymentDomainError as e:
        return error_response("Payment domain error", 400, {"detail": str(e)})
    except ValueError as e:
        return error_response("Invalid UUID format", 400, {
            "detail": str(e),
            "payment_id_received": payment_id_str,
            "refund_id_received": refund_id_str
        })
    except Exception as exc:
        logger.exception("Mark as refunded failed for payment_id: %s", payment_id_str)
        return error_response("Failed to mark payment as refunded", 500, {"detail": str(exc)})