from django.http import JsonResponse
from payment_service.auth.jwt_verifier import JWTVerifier
from rest_framework.exceptions import AuthenticationFailed
from asgiref.sync import async_to_sync

class JWTAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.verify = async_to_sync(JWTVerifier.verify_token_async)

    def __call__(self, request):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            request.user_id = None
            return self.get_response(request)

        if not auth_header.startswith("Bearer "):
            return JsonResponse(
                {"error": "Authorization header must be 'Bearer <token>'"},
                status=401,
            )

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return JsonResponse({"error": "Token is empty"}, status=401)

        try:
            payload = self.verify(token)
            request.user_id = payload["user_id"]
        except AuthenticationFailed as e:
            return JsonResponse({"error": str(e)}, status=401)

        return self.get_response(request)
