# Generated by Django 4.2.11 on 2025-06-12 18:46

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('game', '0004_game_winner'),
    ]

    operations = [
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, default='')),
                ('is_recurring', models.BooleanField(default=False)),
                ('recurrence_interval_seconds', models.PositiveIntegerField(blank=True, help_text='Recurrence interval stored in seconds', null=True)),
                ('stake', models.DecimalField(decimal_places=2, default=10, max_digits=10)),
                ('is_public', models.BooleanField(default=True)),
                ('is_scheduled', models.BooleanField(default=False)),
                ('scheduled_datetime', models.DateTimeField(blank=True, null=True)),
                ('link', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='owned_groups', to=settings.AUTH_USER_MODEL)),
                ('subscribers', models.ManyToManyField(blank=True, related_name='subscribed_groups', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='GroupGame',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(default=django.utils.timezone.now)),
                ('game', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='group_game', to='game.game')),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='games', to='group.group')),
            ],
        ),
    ]
