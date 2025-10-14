from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
import json

from custom_auth.models import User, AbstractUser, CustomUserManager


class Card(models.Model):
    numbers = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"Bingo Card {self.id}"

class Game(models.Model):
    stake = models.CharField(default='20',max_length=50)
    numberofplayers = models.IntegerField(default=0)
    playerCard = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(auto_now_add=True)
    played = models.CharField(max_length=50,default='Created')
    total_calls = models.IntegerField(default=0)
    called_numbers = models.JSONField(default=dict)
    random_numbers = models.JSONField(default=dict)
    winner_price = models.DecimalField(max_digits=100,default=0,decimal_places=2)
    admin_cut = models.DecimalField(max_digits=100,default=0,decimal_places=2)
    bonus = models.IntegerField(default=0)
    winner = models.IntegerField(default=0)
    winner_card=models.JSONField(default=0)

    def __str__(self) -> str:
        return f"Game number {self.id}"

    def save_random_numbers(self, numbers):
        self.random_numbers = json.dumps(numbers)
        self.save()

    def save_called_numbers(self, numbers):
        self.called_numbers = json.dumps(numbers)
        self.save()

class UserGameParticipation(models.Model):
    user=models.ForeignKey(AbstractUser,on_delete=models.CASCADE, related_name='game_participation')
    game=models.ForeignKey(Game,on_delete=models.CASCADE, related_name='participation')
    times_played=models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together=(('user','game'),)
        indexes=[
            models.Index(fields=['user','game']),
            models.Index(fields=['game']),
        ]

    def __str__(self) -> str:
        return f"{self.user.name} played Game {self.game.id} ({self.times_played} times)"

class Agents(models.Model):
    id = models.BigAutoField(primary_key=True)
    balance = models.DecimalField(max_digits=38, decimal_places=2, blank=True, null=True)
    chat_id = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(blank=True, null=True)
    money_limit = models.DecimalField(max_digits=38, decimal_places=2, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    password = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=255, blank=True, null=True)
    status = models.BooleanField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'agents'


class AgentsAccount(models.Model):
    id = models.BigAutoField(primary_key=True)
    account_number = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(blank=True, null=True)
    payment_method = models.SmallIntegerField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    agents = models.ForeignKey(Agents, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'agents_account'



class PaymentRequest(models.Model):
    id = models.BigAutoField(primary_key=True)
    amount = models.DecimalField(max_digits=38, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    customer_chat_id = models.BigIntegerField(blank=True, null=True)
    customer_phone_number = models.CharField(max_length=255, blank=True, null=True)
    payment_method = models.SmallIntegerField(blank=True, null=True)
    payment_status = models.SmallIntegerField(blank=True, null=True)
    payment_type = models.SmallIntegerField(blank=True, null=True)
    reference_id = models.CharField(max_length=255, blank=True, null=True)
    request_source = models.SmallIntegerField(blank=True, null=True)
    transactionsms = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    user_id = models.CharField(max_length=255, blank=True, null=True)
    agents_account = models.ForeignKey(AgentsAccount, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'payment_request'

class DepositAccount(models.Model):
    deposit_payment_method = models.CharField(
        max_length=255,
        primary_key=True,
        help_text="Payment method type (e.g., CBE, CBE_BIRR, TELEBIRR)"
    )
    account_number = models.CharField(
        max_length=255,
        help_text="The account number associated with the payment method"
    )
    owner_name = models.CharField(
        max_length=255,
        help_text="Name of the account owner"
    )

    class Meta:
        db_table = 'deposit_account'
        managed = False

    def __str__(self):
        return f"{self.deposit_payment_method} - {self.account_number}"
class CustomAuthAbstractuser(AbstractBaseUser):  # ✅ Inherit from AbstractBaseUser
    id = models.BigAutoField(primary_key=True)
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    phone_number = models.CharField(unique=True, max_length=15)
    name = models.CharField(max_length=100)
    date_joined = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    telegram_id = models.CharField(max_length=100, blank=True, null=True)

    # Django auth settings
    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        managed = False
        db_table = 'custom_auth_abstractuser'

    def __str__(self):
        return self.phone_number

    # ✅ Permissions
    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    @property
    def is_anonymous(self):
        return False

    @property
    def is_authenticated(self):
        return True


class CustomAuthUser(models.Model):
    abstractuser_ptr = models.OneToOneField(
        CustomAuthAbstractuser,
        on_delete=models.DO_NOTHING,
        primary_key=True,
        db_column='abstractuser_ptr_id'
    )
    wallet = models.DecimalField(max_digits=10, decimal_places=2)
    bonus = models.DecimalField(max_digits=10, decimal_places=2)

    # New fields added
    reserved_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    no_of_games_played = models.IntegerField(blank=True, null=True)
    no_of_cash_deposited = models.IntegerField(blank=True, null=True)
    total_withdraw_amount_per_day = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    last_withdraw_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'custom_auth_user'
class TransferLog(models.Model):
    from_user=models.ForeignKey(
        CustomAuthUser,
        on_delete=models.CASCADE,
        related_name='transfer_sent',
        db_column='from_abstractuser_ptr_id'
    )
    to_user=models.ForeignKey(
        CustomAuthUser,
        on_delete=models.CASCADE,
        related_name='transfer_received',
        db_column='to_abstractuser_ptr_id'
    )
    amount=models.DecimalField(max_digits=38, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'transfer_log'
    def __str__(self):
        return f"{self.from_user.abstractuser_ptr.name}->{self.to_user.abstractuser_ptr.name}: {self.amount}"
