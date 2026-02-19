import json
import logging
from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from dataclasses import asdict

from src.application.payment.factory import get_payment_query_handler
from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.domain.apps.payment.models import PaymentStatus, PaymentMethod

logger = logging.getLogger(__name__)


def _serialize_dto(dto) -> dict:
    """Serialize PaymentResponseDTO or similar."""
    if hasattr(dto, "to_dict"):
        return dto.to_dict()
    return asdict(dto)


@csrf_exempt
async def get_payment(request, payment_id: UUID):
    """Fetch a payment with owner info."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        handler = get_payment_query_handler()
        dto = await handler.get_payment_with_owner(payment_id)
        return JsonResponse(_serialize_dto(dto), status=200)
    except PaymentNotFoundError:
        return JsonResponse({"error": "Payment not found"}, status=404)
    except Exception as e:
        logger.exception("Failed to fetch payment: %s", payment_id)
        return JsonResponse({"error": "Internal server error"}, status=500)


@csrf_exempt
async def list_payments_by_user(request):
    """List payments for authenticated user (with owner data)."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not hasattr(request, "user_id") or not request.user_id:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    user_id = UUID(request.user_id)
    limit = min(int(body.get("limit", 50)), 500)
    offset = int(body.get("offset", 0))

    # Note: Your handler doesn't support filtering by status/method/currency yet.
    # So we ignore those filters unless you extend the service layer.
    try:
        handler = get_payment_query_handler()
        dtos = await handler.get_payments_by_user_with_owner(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        return JsonResponse([_serialize_dto(dto) for dto in dtos], safe=False, status=200)
    except Exception:
        logger.exception("Failed to list payments for user: %s", user_id)
        return JsonResponse({"error": "Internal server error"}, status=500)


@csrf_exempt
async def list_payments_by_wallet(request):
    """List payments for a wallet (with owner data)."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not hasattr(request, "user_id") or not request.user_id:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    wallet_id_str = body.get("wallet_id")
    if not wallet_id_str:
        return JsonResponse({"error": "Missing 'wallet_id'"}, status=400)

    try:
        wallet_id = UUID(wallet_id_str)
    except ValueError:
        return JsonResponse({"error": "Invalid wallet_id UUID format"}, status=400)

    limit = min(int(body.get("limit", 50)), 500)
    offset = int(body.get("offset", 0))

    try:
        handler = get_payment_query_handler()
        dtos = await handler.get_payments_by_wallet_with_owner(
            wallet_id=wallet_id,
            limit=limit,
            offset=offset,
        )
        return JsonResponse([_serialize_dto(dto) for dto in dtos], safe=False, status=200)
    except Exception:
        logger.exception("Failed to list payments for wallet: %s", wallet_id)
        return JsonResponse({"error": "Internal server error"}, status=500)


@csrf_exempt
async def check_payment_exists(request):
    """Check if a payment exists."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    payment_id_str = body.get("payment_id")
    if not payment_id_str:
        return JsonResponse({"error": "Missing 'payment_id'"}, status=400)

    try:
        payment_id = UUID(payment_id_str)
    except ValueError:
        return JsonResponse({"error": "Invalid UUID format"}, status=400)

    try:
        handler = get_payment_query_handler()
        exists = await handler.payment_exists(payment_id)
        return JsonResponse({"exists": exists}, status=200)
    except Exception:
        logger.exception("Failed to check existence for: %s", payment_id_str)
        return JsonResponse({"error": "Internal server error"}, status=500)

