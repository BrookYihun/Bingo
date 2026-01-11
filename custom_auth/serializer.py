# serializers.py
from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'phone_number', 'telegram_id','wallet','is_affiliate', 'affiliate_wallet', 'date_joined']  # Include any fields you need

        #