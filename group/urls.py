# urls.py
from django.urls import path
from .views import GroupCreateUpdateView, my_groups, private_groups, public_groups

urlpatterns = [
    path('create-group/', GroupCreateUpdateView.as_view(), name='group-create'),
    path('my/',my_groups, name='my-groups'),
    path('public/', public_groups, name='public-groups'),
    path('private/', private_groups, name='private-groups'),
]
