from django.http import JsonResponse

async def test_jwt_user_id(request):
    return JsonResponse({
        "user_id_from_jwt": request.user_id
    })
