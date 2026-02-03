from django.contrib import admin
from .models import Card, Game, CustomAuthUser
# Register your models here.

admin.site.register(Game)
admin.site.register(Card)

@admin.register(CustomAuthUser)
class CustomAuthUserAdmin(admin.ModelAdmin):
    search_fields = "abstractuser_ptr", 'abstractuser_ptr__phone_number'