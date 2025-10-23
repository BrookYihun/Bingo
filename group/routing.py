from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/group-socket/(?P<group>[^/]+)/$', consumers.GroupConsumer.as_asgi()),
]
