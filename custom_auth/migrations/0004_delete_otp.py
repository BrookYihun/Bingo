# Generated by Django 5.1.2 on 2025-01-03 16:48

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('custom_auth', '0003_otp_abstractuser_is_verified'),
    ]

    operations = [
        migrations.DeleteModel(
            name='OTP',
        ),
    ]
