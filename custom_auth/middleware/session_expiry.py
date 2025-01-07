from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse

class SessionExpiryMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.session.session_key:  # No session exists
            return JsonResponse({"error": "Session Expired"}, status=403)
