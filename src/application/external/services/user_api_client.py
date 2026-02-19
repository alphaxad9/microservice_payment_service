from uuid import UUID
from src.application.external.user_view import UserView
from django.conf import settings
from .http_client import HTTPClient
import logging

logger = logging.getLogger(__name__)


class UserAPIClient:
    """
    Production-ready client for talking to the AUTH service.
    Handles both:
      { "user": { ... } }
    and:
      { "id": "...", ... }
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client
        self.base_url = settings.AUTH_SERVICE_URL.rstrip("/")

    def get_user_by_id(self, user_id: UUID) -> UserView:
        url = f"{self.base_url}/users/users/{user_id}/"

        try:
            data = self.http.get(url)
            user_data = data.get("user", data)

            # ✅ Fix: Check for 'user_id', not 'id'
            if "user_id" not in user_data or "username" not in user_data:
                raise ValueError(f"Invalid user payload received: {user_data}")

            return UserView(
                user_id=UUID(user_data["user_id"]),
                username=user_data["username"],
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", ""),
            )

        except Exception as e:
            logger.error(f"[UserAPIClient] Failed to fetch user {user_id}: {e}", exc_info=True)
            raise