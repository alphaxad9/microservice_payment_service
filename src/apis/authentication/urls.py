from django.urls import path
from .views import test_jwt_user_id

urlpatterns = [
    path("test/", test_jwt_user_id, name="test-jwt-user-id"),
]