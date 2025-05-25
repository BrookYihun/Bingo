# urls.py
from django.urls import path
from .views import GroupCreateUpdateView

urlpatterns = [
    path('/create-group', GroupCreateUpdateView.as_view(), name='group-create'),
]
