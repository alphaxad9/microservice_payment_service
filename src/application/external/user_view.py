# src/application/external/user_view.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from uuid import UUID


@dataclass(frozen=True)
class UserView:
    """
    Lightweight read-only DTO for referencing a user (e.g., who liked something).
    Contains only minimal user info needed for display.
    Avoids tight coupling to the full User domain model or other UserDTOs.
    """
    user_id: UUID
    username: str
    first_name: str = ""
    last_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        full_name = f"{self.first_name} {self.last_name}".strip() or None
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": full_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserView":
        user_id = data["user_id"]
        if isinstance(user_id, str):
            user_id = UUID(user_id)

        return cls(
            user_id=user_id,
            username=data["username"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )

    @classmethod
    def from_user_id(cls, user_id: UUID) -> "UserView":
        """
        Create a placeholder UserView when only the user_id is available.
        In a real system, this would typically be hydrated via a user query service.
        """
        user_id_str = str(user_id)
        return cls(
            user_id=user_id,
            username=f"user_{user_id_str[:8]}",
            first_name=f"User{user_id_str[:4]}",
            last_name=f"Test{user_id_str[4:8]}",
        )