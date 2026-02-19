import jwt
import httpx
import time
import logging
from asyncio import Lock
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class JWTVerifier:
    _public_key_cache = None
    _last_fetch_time = 0
    _cache_ttl = 300
    _lock = Lock()

    @classmethod
    async def _fetch_public_key(cls):
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(settings.AUTH_PUBLIC_KEY_URL)
            response.raise_for_status()
            key = response.text.strip()

        if not key.startswith("-----BEGIN PUBLIC KEY-----"):
            raise AuthenticationFailed("Invalid public key format")

        return key

    @classmethod
    async def get_public_key(cls):
        now = time.time()
        async with cls._lock:
            if cls._public_key_cache and (now - cls._last_fetch_time) < cls._cache_ttl:
                return cls._public_key_cache

            key = await cls._fetch_public_key()
            cls._public_key_cache = key
            cls._last_fetch_time = now
            return key

    @classmethod
    async def verify_token_async(cls, token: str):
        if token.count(".") < 2:
            raise AuthenticationFailed("Invalid JWT format")

        try:
            public_key = await cls.get_public_key()
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={
                    "verify_exp": True,
                    "verify_aud": False,
                    "verify_iss": False,
                    "require": ["user_id"],
                },
            )
            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token")
