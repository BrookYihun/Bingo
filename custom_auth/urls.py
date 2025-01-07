from django.urls import path
from .views import RegisterView, LoginView, SendOTPView, VerifyOTPView, get_balance, refresh_session, verify_token
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("verify-token/",verify_token,name="verify_token"),
    path("get-balance/",get_balance,name="get_balance"),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('refresh-session/', refresh_session, name='refresh_session'),
]
