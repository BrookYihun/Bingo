import base64
from django.http import HttpResponseForbidden
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class RegisterView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        password = request.data.get('password')
        name = request.data.get('name')

        # Validate the input
        if not phone_number or not password or not name:
            return Response(
                {"error": "Phone number, name, and password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if the phone number already exists
        if User.objects.filter(phone_number=phone_number).exists():
            return Response(
                {"error": "Phone number already in use"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create a new user
        user = User.objects.create_user(phone_number=phone_number, password=password, name=name)
        return Response(
            {"message": "User registered successfully"},
            status=status.HTTP_201_CREATED
        )

class LoginView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        password = request.data.get('password')

        # Authenticate the user
        user = authenticate(phone_number=phone_number, password=password)
        if user:
            tokens = get_tokens_for_user(user)
            return Response(tokens, status=status.HTTP_200_OK)
        
        return Response(
            {"error": "Invalid phone number or password"},
            status=status.HTTP_400_BAD_REQUEST
        )

def custom_csrf_protect(view_func):
    """
    Decorator for views that checks the request for a custom CSRF token.
    """
    def _wrapped_view(request, *args, **kwargs):
        # Retrieve the custom token from the request
        custom_token = request.META.get('HTTP_X_CUSTOM_CSRF_TOKEN')

        if not custom_token:
            # Handle missing token
            return HttpResponseForbidden('CSRF token missing')

        # Retrieve the user based on authentication (assuming user is authenticated)
        user = request.user

        if not user.is_authenticated:
            # Handle unauthenticated users
            return HttpResponseForbidden('User is not authenticated')

        # Retrieve the expected token from the database or wherever it's stored

        decoded_custom_token = base64.b64decode(custom_token)

        parts = decoded_custom_token.split(':')

        if len(parts)!=2:
            return HttpResponseForbidden('Invalid CSRF token')
        
        check_user = authenticate(request, username=parts[0], password=parts[1])

        if check_user is None or check_user.is_authenticated is False:
            # Handle invalid token
            return HttpResponseForbidden('Invalid CSRF token')

        # Call the actual view function if the token is valid
        return view_func(request, *args, **kwargs)

    return _wrapped_view