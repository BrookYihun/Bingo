# Generated by Django 4.2.22 on 2025-06-08 14:25

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('custom_auth', '0005_abstractuser_telgram_id_user_bonus_delete_cashier'),
    ]

    operations = [
        migrations.AlterField(
            model_name='abstractuser',
            name='telgram_id',
            field=models.CharField(max_length=100, null=True),
        ),
    ]
