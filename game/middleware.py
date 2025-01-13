import jwt
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from django.contrib.auth.models import AnonymousUser
from channels.middleware import BaseMiddleware
from urllib.parse import parse_qs


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom WebSocket middleware for JWT authentication.
    """

    async def __call__(self, scope, receive, send):
        # Extract the token from the query string
        query_string = parse_qs(scope["query_string"].decode("utf-8"))
        token = query_string.get("token", [None])[0]

        if token:
            try:
                # Decode and authenticate the token
                validated_token = JWTAuthentication().get_validated_token(token)
                user = JWTAuthentication().get_user(validated_token)
                scope["user"] = user
            except (InvalidToken, jwt.ExpiredSignatureError):
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
