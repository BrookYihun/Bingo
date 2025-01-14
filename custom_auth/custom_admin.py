from django.contrib.admin import AdminSite
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.core.exceptions import PermissionDenied

class CustomAdminSite(AdminSite):
    def has_permission(self, request):
        """
        Check if the user has permissions to access the admin site.
        Uses JWT for authentication instead of session-based middleware.
        """
        try:
            auth = JWTAuthentication()
            validated_user, _ = auth.authenticate(request)
            if validated_user and validated_user.is_staff:
                request.user = validated_user
                return True
        except Exception:
            pass
        raise PermissionDenied("Authentication required to access the admin interface.")

# Instantiate the custom admin site
custom_admin_site = CustomAdminSite(name="custom_admin")
