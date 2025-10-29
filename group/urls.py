# urls.py
from django.urls import path
from .views import GroupCreateUpdateView, my_groups, owner_dashboard, private_groups, public_groups, request_group_withdrawal, subscribe_to_group, subscribe_via_referral, unsubscribe_from_group, withdrawal_history

urlpatterns = [
    path('group/', GroupCreateUpdateView.as_view(), name='group-create'),
    path('group/<int:group_id>/', GroupCreateUpdateView.as_view(), name='group-detail'),
    path('my/',my_groups, name='my-groups'),
    path('public/', public_groups, name='public-groups'),
    path('private/', private_groups, name='private-groups'),
    path("subscribe/", subscribe_to_group, name="subscribe-group"),
    path("unsubscribe/", unsubscribe_from_group, name="unsubscribe-group"),
    path("subscribe_referral/", subscribe_via_referral, name="subscribe-group-referral"),
    path("dashboard/owner/",owner_dashboard, name="owner-dashboard"),
    path("withdraw-history/",withdrawal_history, name="withdraw-history"),
    path("withdraw-request/",request_group_withdrawal, name="withdraw-request"),
]
