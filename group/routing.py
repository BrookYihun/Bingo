from django.urls import path
from . import consumers  # you'll create this next

websocket_urlpatterns = [
    path(r'ws/group-socket/(?P<group_id>[^/]+)/$', consumers.GroupConsumer.as_asgi()),
]
