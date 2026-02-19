
from django.urls import path, include

urlpatterns = [
        path('payment_service/authentication/', include('src.apis.authentication.urls')), 
        path('payment_service/payments/', include('src.apis.payment.urls')),
        path('payment_service/idempotency/', include('src.apis.idempotency.urls')),
        path('health/', include('src.apis.health.urls')),
]
