from django.db import models
from custom_auth.models import User

class AffiliateWithdrawRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='affiliate_withdrawals')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.SmallIntegerField(default=0)  # 0: Pending, 1: Approved, 2: Rejected
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Withdrawal {self.reference_number} - {self.user.name} ({self.amount})"
    class Meta:
        db_table = "affiliate_withdraw_request"
