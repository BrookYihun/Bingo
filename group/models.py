from django.utils import timezone
from django.db import models
from django.conf import settings

class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(default='', blank=True)
    
    is_recurring = models.BooleanField(default=False)
    recurrence_interval_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Recurrence interval stored in seconds"
    )

    stake = models.DecimalField(max_digits=10, decimal_places=2,default=10)
    is_public = models.BooleanField(default=True)  # public/private group

    is_scheduled = models.BooleanField(default=False)  # whether to start at scheduled time
    scheduled_datetime = models.DateTimeField(blank=True, null=True)

    link = models.CharField(max_length=255, unique=True, null=True, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_groups'
    )

    subscribers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='subscribed_groups',
        blank=True
    )

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class GroupGame(models.Model):
    group = models.ForeignKey(
        'Group',
        on_delete=models.SET_NULL,  # Or models.PROTECT, depending on your logic
        null=True,
        blank=True,
        related_name='games'
    )
    game = models.OneToOneField(
        'game.Game',
        on_delete=models.CASCADE,  # If game is deleted, remove the groupgame record
        related_name='group_game'
    )
    start_time = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.game} in {self.group.name if self.group else 'No Group'}"

