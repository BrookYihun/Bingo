#serializer.py

from rest_framework import serializers
from .models import Group, GroupWithdrawRequest
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

# serializers.py

from game.models import Game

class GameHistoryItemSerializer(serializers.ModelSerializer):
    winner_name = serializers.SerializerMethodField()
    class Meta:
        model = Game
        fields = [
            'id', 'stake', 'numberofplayers', 'winner_price', 'bonus',
            'started_at', 'played', 'winner_name'
        ]
        read_only_fields = fields

    def get_winner_name(self, obj):
        # Your Game.winner is likely an integer user ID (0 if none)
        if hasattr(obj, 'winner') and obj.winner and obj.winner != 0:
            try:
                from custom_auth.models import User
                user = User.objects.get(id=obj.winner)
                return getattr(user, 'name', f"User {obj.winner}")
            except Exception:
                return "Unknown"
        return None


# serializers.py

class OwnerGroupDashboardSerializer(serializers.ModelSerializer):
    # subscribers_count comes from .annotate() in the view
    subscribers_count = serializers.IntegerField(read_only=True)
    recent_games = serializers.SerializerMethodField()
    current_game = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'description', 'is_public', 'stake',
            'referral_code', 'group_wallet', 'is_active',
            'created_at', 'scheduled_datetime', 'is_recurring',
            'recurrence_interval_seconds', 'number_of_patterns',
            'subscribers_count', 'recent_games', 'current_game'
        ]
        read_only_fields = fields

    def get_recent_games(self, obj):
        # obj.recent_games is pre-attached in the view
        return GameHistoryItemSerializer(obj.recent_games, many=True).data

    def get_current_game(self, obj):
        from game.models import Game
        game = Game.objects.filter(
            group_game__group=obj
        ).exclude(played='closed').order_by('-started_at').first()
        if game:
            return {
                'id': game.id,
                'stake': float(game.stake),
                'numberofplayers': game.numberofplayers,
                'winner_price': float(game.winner_price),
                'played': game.played,
                'started_at': game.started_at,
                'winner': game.winner if game.winner != 0 else None
            }
        return None

class GroupWithdrawRequestSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True)
    status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, coerce_to_string=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = GroupWithdrawRequest
        fields = [
            'id',
            'group_name',
            'amount',
            'status_display',
            'payment_status',  # raw value if needed
            'created_at',
            'updated_at',
            'transaction_sms'
        ]