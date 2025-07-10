import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from game.middleware import JWTAuthMiddleware
from game.routing import websocket_urlpatterns as game_ws
from group.routing import websocket_urlpatterns as group_ws

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bingo.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(game_ws + group_ws)
    ),
})
