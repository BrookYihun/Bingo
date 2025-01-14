from django.contrib import admin

from custom_auth.models import AbstractUser, Cashier, User

# Register your models here.

admin.site.register(AbstractUser)
admin.site.register(User)
admin.site.register(Cashier)

from django.contrib.admin import AdminSite
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

class CustomAdminSite(AdminSite):
    def has_permission(self, request):
        try:
            jwt_auth = JWTAuthentication()
            user, _ = jwt_auth.authenticate(request)
            if user and user.is_active and user.is_staff:
                return True
        except AuthenticationFailed:
            return False
        return False

# Replace the default admin site
custom_admin_site = CustomAdminSite()



