from django.utils import timezone
from django.db import models
from django.conf import settings
def generate_referral_code(is_public: bool):
    """
    Generate a unique referral code starting at 6 digits (PU000001 / PR000001),
    and expand to 7, 8, 9... digits when the previous range is exceeded.
    """
    prefix = "PU" if is_public else "PR"
    last_group = Group.objects.filter(is_public=is_public).order_by("-id").first()

    if not last_group or not getattr(last_group, "referral_code", None):
        return f"{prefix}000001"

    last_code = last_group.referral_code.replace(prefix, "")
    try:
        number = int(last_code)
    except ValueError:
        number = 0

    number += 1

    # Determine number of digits: start at 6, expand as needed
    digits = max(6, len(str(number)))
    return f"{prefix}{number:0{digits}d}"


class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(default='', blank=True)
    
    is_recurring = models.BooleanField(default=False)
    recurrence_interval_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Recurrence interval stored in seconds"
    )
    scheduled_datetime = models.DateTimeField(blank=True, null=True)

    stake = models.DecimalField(max_digits=10, decimal_places=2,default=10)
    is_public = models.BooleanField(default=True)  # public/private group

    number_of_patterns = models.IntegerField(default=1)

    referral_code = models.CharField(max_length=255, unique=True, null=True, blank=True)

    group_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.5)
    group_wallet = models.DecimalField(max_digits=15, decimal_places=2, default=0)

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

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = generate_referral_code(self.is_public)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({'Public' if self.is_public else 'Private'})"


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

