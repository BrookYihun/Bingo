import base64
from django.http import HttpResponseForbidden
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .serializer import UserSerializer  # Make sure you have a serializer for User model
import random
import requests
from django.conf import settings
from .models import OTP


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

        # Generate tokens for the new user
        tokens = get_tokens_for_user(user)
        user_data = UserSerializer(user).data  # Serialize user data

        return Response(
            {"message": "User registered successfully", "tokens": tokens, "user": user_data},
            status=status.HTTP_201_CREATED
        )

class LoginView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        password = request.data.get('password')

        # Authenticate the user
        user = authenticate(phone_number=phone_number, password=password)
        if user:
            if not user.is_verified:
                return Response(
                    {"error": "Not Verfied User! Verify"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            tokens = get_tokens_for_user(user)
            user_data = UserSerializer(user).data  # Serialize user data
            
            # Combine tokens with user data
            response_data = {
                "tokens": tokens,
                "user": user_data,
            }
            return Response(response_data, status=status.HTTP_200_OK)
        
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
        
        if request.user.is_authenticated and not request.user.is_verified:
            # Handle unverfied users
            return HttpResponseForbidden('User is not verfied')           

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

class SendOTPView(APIView):
    def post(self, request):
        phone_number = request.data.get("phone_number")

        if not phone_number:
            return Response({"error": "Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)

        # API parameters
        base_url = settings.OTP_PROVIDER_API_URL + "/challenge"
        token = settings.OTP_PROVIDER_API_KEY
        headers = {'Authorization': f'Bearer {token}'}
        
        # Custom parameters for the request
        # callback = settings.OTP_CALLBACK_URL
        sender = settings.OTP_SENDER_NAME
        # identifier = settings.OTP_IDENTIFIER_ID
        prefix = settings.OTP_MESSAGE_PREFIX
        postfix = settings.OTP_MESSAGE_POSTFIX
        spaces_before = 0
        spaces_after = 0
        ttl = settings.OTP_EXPIRY_TIME
        code_length = 6
        code_type = 1

        # Construct the final URL
        url = (
            f"{base_url}?&sender={sender}&to={phone_number}"
            f"&pr={prefix}&ps={postfix}&sb={spaces_before}"
            f"&sa={spaces_after}&ttl={ttl}&len={code_length}&t={code_type}"
        )

        try:
            # Send the request to the OTP provider
            response = requests.get(url, headers=headers)
            
            print(response)

            if response.status_code == 200:
                result = response.json()
                print(result.get("acknowledge"))
                if result.get("acknowledge") == "success":
                    return Response({"message": "OTP sent successfully"}, status=status.HTTP_200_OK)
                else:
                    error_message = result["response"]["errors"][0] 
                    return Response({"error": f"Failed to send OTP: {str(error_message)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response(
                    {"error": f"Failed to send OTP: HTTP error {response.status_code}, {response.content}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Request failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class VerifyOTPView(APIView):
    def post(self, request):
        phone_number = request.data.get("phone_number")
        otp = request.data.get("otp")

        if not phone_number or not otp:
            return Response({"error": "Phone number and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

        # API parameters
        base_url = settings.OTP_VERIFY_API_URL +"/verify"
        token = settings.OTP_PROVIDER_API_KEY
        headers = {'Authorization': f'Bearer {token}'}
        url = f"{base_url}?to={phone_number}&code={otp}"

        try:
            # Make the API request to verify OTP
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                result = response.json()
                if result.get("acknowledge") == "success":
                    # Verification succeeded
                    try:
                        # Assuming User model has a phone_number field
                        user = User.objects.get(phone_number=phone_number)

                        # Assuming OTP verification method exists in User model
                        user.verify_otp()

                        # Delete OTP record from local DB (optional if not needed anymore)
                        OTP.objects.filter(phone_number=phone_number, otp=otp).delete()

                        return Response({"message": "OTP verified successfully"}, status=status.HTTP_200_OK)
                    except User.DoesNotExist:
                        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
                else:
                    return Response({"error": "Invalid OTP or verification failed"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(
                    {"error": f"Failed to verify OTP: HTTP error {response.status_code}, {response.content}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except requests.exceptions.RequestException as e:
            return Response({"error": f"Request failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)