import requests
from typing import Any, Dict, Optional
from django.conf import settings

class HTTPClient:
    """
    Reusable HTTP client for service-to-service communication.
    Now uses internal API key instead of JWT.
    """
    def __init__(self, timeout: int = 10):  # increased timeout for prod
        self.timeout = timeout
        self.session = requests.Session()  # reuse connections

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        headers = headers or {}
        headers["X-Internal-Key"] = settings.INTERNAL_API_KEY
        # Optional: add User-Agent for debugging
        headers.setdefault("User-Agent", "wallet-service/1.0")

        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Better logging
            raise RuntimeError(f"Failed to call {url}: {e}") from e