
class JWTAuthMiddleware:
    from channels.db import database_sync_to_async
    def __init__(self, inner):
        self.inner = inner

    def __call__(self, scope, receive, send):
        return self.inner(scope, receive, send)

    async def __call__(self, scope, receive, send):
        # Get the token from the query string
        from django.contrib.auth.models import AnonymousUser

        query_string = scope.get("query_string", b"").decode("utf-8")
        token = self.get_token_from_query_string(query_string)

        # Authenticate the user
        if token:
            validated_token = self.validate_token(token)
            if validated_token:
                user = await self.get_user(validated_token)
                scope["user"] = user
            else:
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)

    @staticmethod
    def get_token_from_query_string(query_string):
        """
        Extracts the token from the query string.
        """
        for param in query_string.split("&"):
            key, _, value = param.partition("=")
            if key == "token":
                return value
        return None

    def validate_token(self, token):
        """
        Validates the token using JWTAuthentication.
        """
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            jwt_auth = JWTAuthentication()
            validated_token = jwt_auth.get_validated_token(token)
            return validated_token
        except Exception:
            return None

    @database_sync_to_async
    def get_user(self, validated_token):
        """
        Fetches the user asynchronously using the validated token.
        """
        from rest_framework_simplejwt.authentication import JWTAuthentication
        return JWTAuthentication().get_user(validated_token)
