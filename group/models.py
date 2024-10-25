import uuid
from django.db import models
from custom_auth.models import AbstractUser

class Group(models.Model):
    GROUP_PRIVACY_CHOICES = (
        ('public', 'Public'),
        ('private', 'Private'),
    )

    name = models.CharField(max_length=100, unique=True)
    link = models.CharField(max_length=255, unique=True, blank=True, null=True)  # Store unique invitation link for private groups
    privacy = models.CharField(max_length=7, choices=GROUP_PRIVACY_CHOICES, default='public')
    owner = models.ForeignKey(AbstractUser, related_name='owned_groups', on_delete=models.CASCADE)
    members = models.ManyToManyField(AbstractUser, related_name='group_members', through='GroupMembership')
    
    def save(self, *args, **kwargs):
        if self.privacy == 'private' and not self.link:
            # Generate a unique link if the group is private and doesn't already have a link
            self.link = uuid.uuid4().hex
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    user = models.ForeignKey(AbstractUser, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_owner = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'group')

    def __str__(self):
        return f"{self.user} in {self.group}"
