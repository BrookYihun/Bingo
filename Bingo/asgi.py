"""
ASGI config for dallolbingo project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

from game import routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bingo.settings')

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})

from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
application = ASGIStaticFilesHandler(application)