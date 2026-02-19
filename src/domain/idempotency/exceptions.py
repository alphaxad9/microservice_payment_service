# src/domain/idempotency/exceptions.py
from __future__ import annotations
from typing import Any, Optional
class IdempotencyDomainError(Exception):
    """Base exception for all idempotency-related domain errors."""
    pass

class IdempotencyKeyError(IdempotencyDomainError, ValueError):
    """Base class for errors related to the idempotency key itself."""
    pass

class InvalidIdempotencyKeyFormatError(IdempotencyKeyError):
    """Raised when the idempotency key is missing, empty, or does not meet format requirements."""
    def __init__(self, key: Optional[str] = None, message: Optional[str] = None):
        if message is None:
            if key is None or key == "":
                message = "Idempotency key is required and must be a non-empty string"
            else:
                message = f"Invalid idempotency key format: '{key}'"
        self.key = key
        super().__init__(message)

class IdempotencyKeyTooLongError(IdempotencyKeyError):
    """Raised when the idempotency key exceeds the maximum allowed length (e.g., for DB constraints)."""
    def __init__(self, key: str, max_length: int = 255, message: Optional[str] = None):
        if message is None:
            message = f"Idempotency key exceeds maximum length of {max_length} characters (got {len(key)})"
        self.key = key
        self.max_length = max_length
        super().__init__(message)

class IdempotencyKeyExpiredError(IdempotencyDomainError):
    """Raised when attempting to use or lock an already expired idempotency key."""
    def __init__(self, key: str, message: Optional[str] = None):
        if message is None:
            message = f"Idempotency key '{key}' has expired and cannot be used"
        self.key = key
        super().__init__(message)

class IdempotencyKeyAlreadyUsedError(IdempotencyDomainError):
    """Raised when trying to process a request with a key that has already been successfully used."""
    def __init__(self, key: str, message: Optional[str] = None):
        if message is None:
            message = f"Idempotency key '{key}' has already been used"
        self.key = key
        super().__init__(message)

class IdempotencyKeyInProgressError(IdempotencyDomainError):
    """Raised when a duplicate request arrives while the original is still being processed."""
    def __init__(self, key: str, message: Optional[str] = None):
        if message is None:
            message = f"Request with idempotency key '{key}' is already in progress"
        self.key = key
        super().__init__(message)

class IdempotencyKeyAlreadyLockedError(IdempotencyDomainError):
    """Raised when trying to acquire a lock on a key that is already locked."""
    def __init__(self, key: str, locked_by: Optional[Any] = None, message: Optional[str] = None):
        if message is None:
            message = f"Idempotency key '{key}' is already locked"
            if locked_by is not None:
                message += f" by {locked_by}"
        self.key = key
        self.locked_by = locked_by
        super().__init__(message)

class IdempotencyKeyReuseWithDifferentPayloadError(IdempotencyDomainError):
    """
    Critical security/validation error.
    Raised when the same idempotency key is used with a different request payload/fingerprint.
    """
    def __init__(self, key: str, message: Optional[str] = None):
        if message is None:
            message = (
                f"Idempotency key '{key}' was previously used with different request parameters. "
                "Reusing a key with changed data is not allowed."
            )
        self.key = key
        super().__init__(message)

class IdempotencyKeyNotFoundError(IdempotencyDomainError, LookupError):
    """Raised when a requested idempotency key does not exist in storage."""
    def __init__(self, key: Optional[str] = None, message: Optional[str] = None):
        if message is None:
            message = "Idempotency key not found" + (f": '{key}'" if key else "")
        self.key = key
        super().__init__(message)


class IdempotencyKeyAlreadyExistsError(IdempotencyDomainError):
    """Raised during creation when a key already exists (e.g., race condition resolved at DB level)."""
    def __init__(self, key: str, user_id: Optional[Any] = None, message: Optional[str] = None):
        if message is None:
            message = f"Idempotency key '{key}' already exists"
            if user_id is not None:
                message += f" for user {user_id}"
        self.key = key
        self.user_id = user_id
        super().__init__(message)


class IdempotencyResponseMissingError(IdempotencyDomainError):
    """Raised when trying to replay a response but no stored response exists (data corruption or bug)."""
    def __init__(self, key: str, message: Optional[str] = None):
        if message is None:
            message = f"No stored response available for replay on idempotency key '{key}'"
        self.key = key
        super().__init__(message)


class IdempotencyKeyExpirationInPastError(IdempotencyDomainError):
    """Raised when trying to create a key with an expires_at timestamp that is not in the future."""
    def __init__(self, expires_at: Optional[str] = None, message: Optional[str] = None):
        if message is None:
            message = "Idempotency key expiration time must be in the future"
            if expires_at:
                message += f" (got: {expires_at})"
        self.expires_at = expires_at
        super().__init__(message)


class IdempotencyInvalidStateTransitionError(IdempotencyDomainError):
    """Raised when an invalid state transition is attempted on an IdempotencyKey aggregate."""
    def __init__(self, key: str, current_status: str, attempted_action: str, message: Optional[str] = None):
        if message is None:
            message = (
                f"Invalid state transition for idempotency key '{key}': "
                f"cannot {attempted_action} when status is '{current_status}'"
            )
        self.key = key
        self.current_status = current_status
        self.attempted_action = attempted_action
        super().__init__(message)