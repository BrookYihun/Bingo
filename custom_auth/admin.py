from django.contrib import admin

from custom_auth.models import AbstractUser, User

# Register your models here.

admin.site.register(AbstractUser)

admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass




