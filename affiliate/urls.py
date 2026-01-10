from django.urls import path
from .views import AffiliateReferralsView, AffiliateTransactionsView, AffiliateWithdrawView, AffiliateWithdrawHistoryView

urlpatterns = [
    path('referrals/', AffiliateReferralsView.as_view(), name='affiliate-referrals'),
    path('transactions/', AffiliateTransactionsView.as_view(), name='affiliate-transactions'),
    path('withdraw/', AffiliateWithdrawView.as_view(), name='affiliate-withdraw'),
    path('withdraw-history/', AffiliateWithdrawHistoryView.as_view(), name='affiliate-withdraw-history'),
]
