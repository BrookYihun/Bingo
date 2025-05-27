# urls.py
from django.urls import path
from .views import GroupCreateUpdateView, my_groups, private_groups, public_groups, subscribe_to_group, unsubscribe_from_group

urlpatterns = [
    path('group/', GroupCreateUpdateView.as_view(), name='group-create'),
    path('group/<int:group_id>/', GroupCreateUpdateView.as_view(), name='group-detail'),
    path('my/',my_groups, name='my-groups'),
    path('public/', public_groups, name='public-groups'),
    path('private/', private_groups, name='private-groups'),
    path("subscribe/", subscribe_to_group, name="subscribe-group"),
    path("unsubscribe/", unsubscribe_from_group, name="unsubscribe-group"),
]
