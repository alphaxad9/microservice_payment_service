from __future__ import annotations

from src.application.idempotency.handlers.idempotency_command_handlers import IdempotencyCommandHandler
from src.application.idempotency.handlers.idempotency_query_handlers import IdempotencyQueryHandler
from src.application.idempotency.services.idempotency_command_service import IdempotencyCommandService
from src.application.idempotency.services.idempotency_query_services import IdempotencyQueryService


# ------------------------------------------------------------------
# Repository Factories (Infrastructure Layer)
# ------------------------------------------------------------------

def get_idempotency_command_repository():
    """Factory for the write-side idempotency key repository."""
    from src.infrastructure.repos.idempontency.idempotence_command_repo import DjangoIdempotencyKeyCommandRepository
    return DjangoIdempotencyKeyCommandRepository()


def get_idempotency_query_repository():
    """Factory for the read-side idempotency key repository."""
    from src.infrastructure.repos.idempontency.idempotence_query_repo import DjangoIdempotencyKeyQueryRepository
    return DjangoIdempotencyKeyQueryRepository()


# ------------------------------------------------------------------
# Service Factories
# ------------------------------------------------------------------

def get_idempotency_command_service() -> IdempotencyCommandService:
    """Constructs the command-side idempotency service with required repositories."""
    command_repo = get_idempotency_command_repository()
    query_repo = get_idempotency_query_repository()
    return IdempotencyCommandService(
        command_repo=command_repo,
        query_repo=query_repo,
    )


def get_idempotency_query_service() -> IdempotencyQueryService:
    """Constructs the query-side idempotency service."""
    query_repo = get_idempotency_query_repository()
    return IdempotencyQueryService(query_repository=query_repo)


# ------------------------------------------------------------------
# Handler Factories
# ------------------------------------------------------------------

def get_idempotency_command_handler() -> IdempotencyCommandHandler:
    """
    Returns a fully wired command handler for idempotency operations.
    Used by payment command handlers and middleware to manage request deduplication.
    """
    command_service = get_idempotency_command_service()
    return IdempotencyCommandHandler(command_service=command_service)


def get_idempotency_query_handler() -> IdempotencyQueryHandler:
    """
    Returns a query handler for inspecting idempotency keys (e.g., in admin or monitoring).
    """
    query_service = get_idempotency_query_service()
    return IdempotencyQueryHandler(idempotency_queries=query_service)