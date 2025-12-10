import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from game.middleware import JWTAuthMiddleware
# from game.routing import websocket_urlpatterns as game_ws
from group.routing import websocket_urlpatterns as group_ws
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bingo.settings')

# Combine all websocket routes
all_ws_routes = group_ws

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(all_ws_routes)
    ),
})

application = ASGIStaticFilesHandler(application)
