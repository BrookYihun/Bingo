# Generated by Django 5.1.1 on 2024-10-04 17:16

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AbstractUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('phone_number', models.CharField(max_length=15, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('date_joined', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Cashier',
            fields=[
                ('abstractuser_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL)),
                ('location', models.CharField(max_length=15, unique=True)),
            ],
            options={
                'abstract': False,
            },
            bases=('custom_auth.abstractuser',),
        ),
        migrations.CreateModel(
            name='User',
            fields=[
                ('abstractuser_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL)),
                ('wallet', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
            ],
            options={
                'abstract': False,
            },
            bases=('custom_auth.abstractuser',),
        ),
    ]
