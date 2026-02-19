# src/application/idempotency/views/query_views.py

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime

from src.application.idempotency.factory import get_idempotency_query_handler
from src.domain.idempotency.models import IdempotencyStatus
from src.domain.idempotency.exceptions import IdempotencyKeyNotFoundError

logger = logging.getLogger(__name__)


def _ensure_user_id(request) -> UUID:
    if not hasattr(request, "user_id") or not request.user_id:
        raise ValueError("Authentication required")
    return UUID(request.user_id)


def _serialize_idempotency_key(key) -> Dict[str, Any]:
    """Convert an IdempotencyKey domain object to a JSON-serializable dict."""
    return {
        "idempotency_id": str(key.idempotency_id),
        "key": key.key,
        "user_id": str(key.user_id),
        "fingerprint": key.fingerprint,
        "status": key.status.name,
        "created_at": key.created_at.isoformat() if key.created_at else None,
        "updated_at": key.updated_at.isoformat() if key.updated_at else None,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "locked_until": key.locked_until.isoformat() if key.locked_until else None,
        "locked_by": key.locked_by,
        "request_id": str(key.request_id) if key.request_id else None,
        "correlation_id": str(key.correlation_id) if key.correlation_id else None,
        "has_response": key.has_response(),
        "response": {
            "status_code": key.response.status_code,
            "headers": key.response.headers,
            "body": key.response.body,
        } if key.response else None,
    }


def _parse_optional_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@csrf_exempt
async def get_idempotency_key_view(request):
    """
    GET /idempotency/keys/<key>/
    Retrieve a specific idempotency key by key string and user_id.
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        user_id = _ensure_user_id(request)
        key_str = request.GET.get("key")
        if not key_str:
            return JsonResponse({"error": "Missing 'key' query parameter"}, status=400)

        handler = get_idempotency_query_handler()
        key_obj = await handler.get_key(key=key_str, user_id=user_id)
        return JsonResponse(_serialize_idempotency_key(key_obj), status=200)

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=401)
    except IdempotencyKeyNotFoundError:
        return JsonResponse({"error": "Idempotency key not found"}, status=404)
    except Exception as e:
        logger.exception("Failed to retrieve idempotency key")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)


@csrf_exempt
async def list_user_idempotency_keys_view(request):
    """
    GET /idempotency/keys/user/
    List all idempotency keys for the authenticated user with pagination.
    Supports optional limit and offset query params.
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        user_id = _ensure_user_id(request)
        limit = _parse_optional_int(request.GET.get("limit"), 100)
        offset = _parse_optional_int(request.GET.get("offset"), 0)

        handler = get_idempotency_query_handler()
        keys = await handler.get_keys_by_user(user_id=user_id, limit=limit, offset=offset)
        return JsonResponse({
            "keys": [_serialize_idempotency_key(k) for k in keys],
            "limit": limit,
            "offset": offset,
            "count": len(keys),
        }, status=200)

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=401)
    except Exception as e:
        logger.exception("Failed to list user idempotency keys")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)


@csrf_exempt
async def list_keys_by_status_view(request):
    """
    GET /idempotency/keys/status/
    List keys by status (e.g., PENDING, COMPLETED, FAILED).
    Query param: status (required), limit, offset.
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    status_str = request.GET.get("status")
    if not status_str:
        return JsonResponse({"error": "Missing 'status' query parameter"}, status=400)

    try:
        status = IdempotencyStatus[status_str.upper()]
    except KeyError:
        return JsonResponse({
            "error": f"Invalid status. Must be one of: {[s.name for s in IdempotencyStatus]}"
        }, status=400)

    try:
        limit = _parse_optional_int(request.GET.get("limit"), 100)
        offset = _parse_optional_int(request.GET.get("offset"), 0)

        handler = get_idempotency_query_handler()
        keys = await handler.get_keys_by_status(status=status, limit=limit, offset=offset)
        return JsonResponse({
            "keys": [_serialize_idempotency_key(k) for k in keys],
            "status": status.name,
            "limit": limit,
            "offset": offset,
            "count": len(keys),
        }, status=200)

    except Exception as e:
        logger.exception("Failed to list keys by status")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)


@csrf_exempt
async def list_expired_keys_view(request):
    """
    GET /idempotency/keys/expired/
    List expired idempotency keys (for monitoring/cleanup).
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        limit = _parse_optional_int(request.GET.get("limit"), 100)
        offset = _parse_optional_int(request.GET.get("offset"), 0)

        handler = get_idempotency_query_handler()
        keys = await handler.get_expired_keys(limit=limit, offset=offset)
        return JsonResponse({
            "keys": [_serialize_idempotency_key(k) for k in keys],
            "limit": limit,
            "offset": offset,
            "count": len(keys),
        }, status=200)

    except Exception as e:
        logger.exception("Failed to list expired keys")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)


@csrf_exempt
async def count_user_keys_view(request):
    """
    GET /idempotency/keys/count/
    Get total count of idempotency keys for the current user.
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        user_id = _ensure_user_id(request)
        handler = get_idempotency_query_handler()
        count = await handler.count_keys_by_user(user_id=user_id)
        return JsonResponse({"user_id": str(user_id), "total_keys": count}, status=200)

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=401)
    except Exception as e:
        logger.exception("Failed to count user keys")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)


@csrf_exempt
async def get_idempotency_metrics_view(request):
    """
    GET /idempotency/metrics/
    Get aggregated metrics between two UTC timestamps.
    Query params: start (ISO 8601), end (ISO 8601)
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    if not start_str or not end_str:
        return JsonResponse({
            "error": "Both 'start' and 'end' (ISO 8601 UTC) are required"
        }, status=400)

    try:
        start_dt = parse_datetime(start_str)
        end_dt = parse_datetime(end_str)

        if start_dt is None or end_dt is None:
            raise ValueError("Invalid datetime format")

        # Ensure timezone-aware UTC
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        if start_dt >= end_dt:
            return JsonResponse({"error": "'start' must be before 'end'"}, status=400)

        handler = get_idempotency_query_handler()
        metrics = await handler.get_key_metrics(start_date=start_dt, end_date=end_dt)
        return JsonResponse(metrics, status=200)

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("Failed to fetch idempotency metrics")
        return JsonResponse({"error": "Internal error", "detail": str(e)}, status=500)