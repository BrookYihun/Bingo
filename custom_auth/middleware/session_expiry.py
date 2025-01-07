from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse

class SessionExpiryMiddleware(MiddlewareMixin):
    def process_request(self, request):
        
        if request.path in ['/api/auth/login/', '/api/auth/register/', '/api/auth/send-otp/', '/api/auth/verify-otp/','/api/auth/verify-token/','/api/auth/refresh-session/']:  # Adjust the URLs accordingly
            return None  # Skip the middleware logic
        
        if not request.session.session_key:  # No session exists
            return JsonResponse({"error": "Session Expired"}, status=403)
