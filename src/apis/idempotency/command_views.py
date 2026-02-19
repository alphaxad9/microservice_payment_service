# src/application/idempotency/views/command_views.py

import json
import logging
from uuid import UUID
from typing import Any, Dict, Optional
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from src.domain.idempotency.models import compute_fingerprint   # ← import this!
from src.application.idempotency.factory import get_idempotency_command_handler
from src.domain.idempotency.exceptions import (
    IdempotencyKeyNotFoundError,
    IdempotencyKeyAlreadyExistsError,
    IdempotencyKeyReuseWithDifferentPayloadError,
)
from uuid import UUID   # ← Add uuid4 here if you want, or just import uuid
import uuid
logger = logging.getLogger(__name__)


def _ensure_user_id(request) -> UUID:
    if not hasattr(request, "user_id") or not request.user_id:
        raise ValueError("Authentication required")
    return UUID(request.user_id)


@csrf_exempt
async def create_test_idempotency_key(request):
    """
    POST /idempotency/test/create/
    Manually create an idempotency key for testing.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        user_id = _ensure_user_id(request)
        body = json.loads(request.body)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=401)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    key = body.get("key")
    payload = body.get("payload", {})
    ttl_hours = body.get("ttl_hours", 24)

    if not key:
        return JsonResponse({"error": "Missing 'key' field"}, status=400)

    # Very useful for robustness in tests
    if isinstance(key, UUID):
        key = str(key)
    elif not isinstance(key, str):
        return JsonResponse({"error": "'key' must be a string (UUID recommended)"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "'payload' must be a JSON object"}, status=400)

    try:
        idempotency_key = await get_idempotency_command_handler().create_idempotency_key(
            key=key.strip(),
            user_id=user_id,
            payload=payload,
            ttl_hours=ttl_hours,
        )
    except IdempotencyKeyAlreadyExistsError:
        return JsonResponse({"error": "Idempotency key already exists"}, status=409)
    except IdempotencyKeyReuseWithDifferentPayloadError as e:
        return JsonResponse({"error": str(e)}, status=409)
    except Exception as e:
        logger.exception("Failed to create test idempotency key")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)

    return JsonResponse({
        "key": idempotency_key.key,
        "user_id": str(idempotency_key.user_id),
        "created_at": idempotency_key.created_at.isoformat() if idempotency_key.created_at else None,
        "expires_at": idempotency_key.expires_at.isoformat() if idempotency_key.expires_at else None,
        "status": idempotency_key.status.name,  # ← FIXED: .name instead of the enum object
    }, status=201)

@csrf_exempt
async def begin_test_processing(request):
    """
    POST /idempotency/test/begin/
    Now requires payload to compute correct fingerprint
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        user_id = _ensure_user_id(request)
        body = json.loads(request.body)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=401)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    key = body.get("key")
    payload = body.get("payload", {})               # ← now required for correct test
    locker_id = body.get("locker_id", str(uuid.uuid4()))

    if not key:
        return JsonResponse({"error": "Missing 'key'"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "'payload' must be a JSON object"}, status=400)

    fingerprint = compute_fingerprint(payload)      # ← this is the key change!

    try:
        cached_response = await get_idempotency_command_handler().begin_request_processing(
            key=key,
            user_id=user_id,
            locker_id=locker_id,
            fingerprint=fingerprint,                   # ← pass it!
        )
    except IdempotencyKeyReuseWithDifferentPayloadError as e:
        return JsonResponse({"error": str(e)}, status=409)  # better status than 500
    except IdempotencyKeyNotFoundError:
        return JsonResponse({"error": "Idempotency key not found"}, status=404)
    except Exception as e:
        logger.exception("Begin processing failed")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)

    return JsonResponse({
        "cached_response": cached_response,  # null if we can proceed
        "fingerprint_used": fingerprint      # optional — nice for debugging
    }, status=200)




@csrf_exempt
async def record_test_failure(request):
    """
    POST /idempotency/test/failure/
    Record a failed outcome (still replayable).
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        user_id = _ensure_user_id(request)
        body = json.loads(request.body)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=401)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    key = body.get("key")
    status_code = body.get("status_code", 400)
    headers = body.get("headers", {})
    response_body = body.get("body", {"error": "Simulated failure"})

    if not key:
        return JsonResponse({"error": "Missing 'key'"}, status=400)

    try:
        await get_idempotency_command_handler().record_failed_response(
            key=key,
            user_id=user_id,
            status_code=status_code,
            headers=headers,
            body=response_body,
        )
    except IdempotencyKeyNotFoundError:
        return JsonResponse({"error": "Idempotency key not found"}, status=404)
    except Exception as e:
        logger.exception("Record failure failed")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)

    return JsonResponse({"message": "Failure recorded"}, status=200)


@csrf_exempt
async def cleanup_expired_keys_view(request):
    """
    POST /idempotency/test/cleanup/
    Trigger cleanup of expired keys (e.g., for testing TTL logic).
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
        older_than_hours = body.get("older_than_hours", 24)
    except json.JSONDecodeError:
        older_than_hours = 24

    try:
        deleted_count = await get_idempotency_command_handler().cleanup_expired_keys(older_than_hours)
    except Exception as e:
        logger.exception("Cleanup failed")
        return JsonResponse({"error": "Cleanup failed", "detail": str(e)}, status=500)

    return JsonResponse({"deleted_count": deleted_count}, status=200)