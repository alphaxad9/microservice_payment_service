from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET"])
def health_check(request):
    """
    Kubernetes health probe endpoint.
    Returns 200 OK when the application is ready to serve traffic.
    """
    return JsonResponse(
        {"status": "ok", "service": "auth"},
        status=200,
        content_type="application/json"
    )