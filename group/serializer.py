from rest_framework import serializers
from .models import Group
from django.contrib.auth import get_user_model

User = get_user_model()

class GroupSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.name', read_only=True)  # assuming your User model has `name`
    subscribers = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field='id'  # or 'username' or 'name', depending on what you need
    )

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'description', 'is_recurring', 'recurrence_interval_seconds',
            'stake', 'is_public', 'scheduled_datetime', 'referral_code', 'number_of_patterns',
            'owner', 'owner_name', 'subscribers', 'created_at'
        ]
