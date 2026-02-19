from django.urls import path
from src.apis.health.views import (
    health_check
)

urlpatterns = [
    path('', health_check, name='health'),
   
]