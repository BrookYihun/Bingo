import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from game.middleware import JWTAuthMiddleware
from game.routing import websocket_urlpatterns
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bingo.settings')

# Define the ASGI application
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})

# Handle static files in ASGI
application = ASGIStaticFilesHandler(application)
