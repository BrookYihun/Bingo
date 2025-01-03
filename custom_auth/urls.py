from django.urls import path
from .views import RegisterView, LoginView, SendOTPView, VerifyOTPView, get_balance, verify_token

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("verify-token/",verify_token,name="verify_token"),
    path("get-blance/",get_balance,name="get_balance"),
]
