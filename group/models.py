from django.db import models
from django.conf import settings
from django.utils.timezone import now

class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    
    is_recurring = models.BooleanField(default=False)
    recurrence_interval_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Recurrence interval stored in seconds"
    )

    stake = models.DecimalField(max_digits=10, decimal_places=2)
    is_public = models.BooleanField(default=True)  # public/private group

    is_scheduled = models.BooleanField(default=False)  # whether to start at scheduled time
    scheduled_datetime = models.DateTimeField(blank=True, null=True)

    group_link = models.CharField(max_length=255, unique=True)

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

    created_at = models.DateTimeField(auto_now_add=True,default=now)

    def __str__(self):
        return self.name
