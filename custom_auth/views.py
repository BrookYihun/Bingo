import base64
import datetime
import json
import random
import string
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User
from rest_framework_simplejwt.tokens import RefreshToken
from .serializer import UserSerializer  # Make sure you have a serializer for User model
import requests
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework.exceptions import ValidationError
from django.contrib.auth import authenticate
import hmac
import hashlib
from urllib.parse import parse_qs, unquote_plus
from django.conf import settings


def get_tokens_for_user(user_id):
    # Retrieve the user object
    user = get_object_or_404(User, id=user_id)
    
    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)
    
    # Return tokens
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

@permission_classes([IsAuthenticated])
def refresh_session(request):
    user_id = request.data.get('user_id')

    # Validate the user ID
    if not user_id or user_id != request.user.id:
        return Response({"error": "Invalid user ID"}, status=status.HTTP_400_BAD_REQUEST)

    tokens = get_tokens_for_user(user_id, request)

    return Response({"tokens": tokens}, status=status.HTTP_200_OK)

# Registration view
@permission_classes([AllowAny])
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

        response = send_otp_for_register(phone_number)
        if response == "success":
            return Response(
                {"message": "OTP Sent"},
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {"error": response},
                status=status.HTTP_400_BAD_REQUEST
            )

# Registration view
def generate_random_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


@permission_classes([AllowAny])
class RegisterTelegramView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        chat_id = request.data.get('chat_id')
        name = request.data.get('name')

        if not phone_number or not chat_id or not name:
            return Response(
                {"error": "Phone number, name, and chat_id are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(phone_number=phone_number)
            # Phone number exists – update chat_id
            user.chat_id = chat_id
            user.save()
        except User.DoesNotExist:
            # Phone number doesn't exist – create new user with random password
            random_password = generate_random_password()
            user = User.objects.create_user(
                phone_number=phone_number,
                name=name,
                password=random_password,
                chat_id=chat_id,
            )

        user.verify_otp()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        user_data = UserSerializer(user).data

        return Response({
            "tokens": {
                "refresh": refresh_token,
                "access": access_token,
            },
            "user": user_data,
        }, status=status.HTTP_200_OK)

class LoginView(APIView):
    permission_classes = [AllowAny]  # Allow unauthenticated users to access this view

    def post(self, request):
        phone_number = request.data.get('phone_number')
        password = request.data.get('password')

        # Authenticate the user
        user = authenticate(phone_number=phone_number, password=password)
        if user:
            if not user.is_verified:
                return Response(
                    {"error": "Not Verified User! Please verify your account."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Generate JWT tokens for the user
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

            # Serialize user data
            user_data = UserSerializer(user).data

            # Combine tokens with user data
            response_data = {
                "tokens": {
                    "refresh": refresh_token,
                    "access": access_token,
                },
                "user": user_data,
            }
            return Response(response_data, status=status.HTTP_200_OK)

        return Response(
            {"error": "Invalid phone number or password"},
            status=status.HTTP_400_BAD_REQUEST
        )

@permission_classes([AllowAny])
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
                    print(result["response"]["errors"])
                    return Response({"error": f"Failed to send OTP: {str(error_message)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response(
                    {"error": f"Failed to send OTP: HTTP error {response.status_code}, {response.content}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Request failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@permission_classes([AllowAny])        
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
                        
                        tokens = get_tokens_for_user(user.id,request)
                        user_data = UserSerializer(user).data

                        return Response({"message": "OTP verified successfully", "tokens": tokens, "user": user_data}, status=status.HTTP_200_OK)
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

    
def send_otp_for_register(phone_number):

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

        if response.status_code == 200:
            result = response.json()
            if result.get("acknowledge") == "success":
                return "success"
            else:
                error_message = result["response"]["errors"][0] 
                return error_message
        else:
            return error_message
        
    except requests.exceptions.RequestException as e:
        return str(e)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_balance(request,user_id):
    """
    Retrieve the wallet balance for the authenticated user.
    """
    try:
        # Access the authenticated user
        user = get_object_or_404(User, id=user_id)

        # Check if the user is verified
        if not user.is_verified:
            return Response({'error': 'User is not verified'}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve the user's wallet balance
        balance = user.wallet

        # Respond with the balance
        return Response({'balance': float(balance)}, status=status.HTTP_200_OK)

    except Exception as e:
        # Handle unexpected errors
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def is_token_not_expired(token, expiration_minutes=30):
    """
    Verify if the given token is not expired.

    Args:
        token (str): The base64-encoded token containing a timestamp.
        expiration_minutes (int): The number of minutes before the token expires.

    Returns:
        bool: True if the token is not expired, False otherwise.
    """
    try:
        # Decode the token
        decoded_token = base64.b64decode(token).decode('utf-8')

        # Extract the timestamp part of the token (assuming token format: "username:password:timestamp")
        parts = decoded_token.split(':')
        if len(parts) < 3:
            return False  # Invalid token format

        # Parse the timestamp
        timestamp = float(parts[2])
        token_time = datetime.datetime.fromtimestamp(timestamp)

        # Check if the token is expired
        current_time = datetime.datetime.now()
        expiration_time = token_time + datetime.timedelta(minutes=expiration_minutes)

        return current_time <= expiration_time

    except (ValueError, IndexError, base64.binascii.Error):
        # Handle decoding or parsing errors
        return False


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_token(request):
    try:
        # Retrieve tokens from the request
        access_token = request.GET.get('access', None)
        refresh_token = request.GET.get('refresh', None)

        # Validate Access Token
        if access_token:
            try:
                AccessToken(access_token)  # Verifies token validity
            except ValidationError:
                return Response({"error": "Invalid or expired access token"}, status=403)
        else:
            return Response({"error": "Access token missing"}, status=403)

        # Validate Refresh Token
        if refresh_token:
            try:
                RefreshToken(refresh_token)  # Verifies token validity
            except ValidationError:
                return Response({"error": "Invalid or expired refresh token"}, status=403)
        else:
            return Response({"error": "Refresh token missing"}, status=403)

        # All tokens are valid
        return Response({"message": "All tokens are valid"}, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=400)


def parse_init_data(init_data: str) -> dict:
    params = parse_qs(init_data, keep_blank_values=True)
    return {k: v[0] for k, v in params.items()}


def bytes_to_hex(b: bytes) -> str:
    return b.hex()

def hmac_sha256(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode('utf-8'), hashlib.sha256).digest()


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_init_data(request):
    init_data = request.data.get("initData")
    bot_token = settings.TELEGRAM_BOT_TOKEN

    if not init_data:
        return Response({"error": "initData is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        params = parse_init_data(init_data)
        print(params)
        received_hash = params.pop("hash", None)

        if not received_hash:
            return Response({"error": "Hash not found in initData"}, status=status.HTTP_400_BAD_REQUEST)

        # Build data_check_string
        keys = sorted(params.keys())
        data_check_string = "\n".join(f"{key}={params[key]}" for key in keys)

        # Generate secret key and calculate hash
        secret_key = hmac_sha256(b"WebAppData", bot_token)
        calculated_hash = bytes_to_hex(
            hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).digest()
        )
        
        print("Calculated hash:", calculated_hash)
        print("Received hash:", received_hash)

        if calculated_hash != received_hash:
            return Response({"verified": False}, status=status.HTTP_403_FORBIDDEN)

        # Extract Telegram user data from `initData`
        user_json = params.get("user")
        if not user_json:
            return Response({"error": "user field not found in initData"}, status=status.HTTP_400_BAD_REQUEST)

        user_data = json.loads(user_json)
        telegram_id = user_data.get("id")

        # Lookup existing user
        try:
            user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            return Response({"error": "User with this telegram_id not found"}, status=status.HTTP_404_NOT_FOUND)

        # Generate tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # Serialize user
        serialized_user = UserSerializer(user).data

        return Response({
            "tokens": {
                "access": access_token,
                "refresh": refresh_token
            },
            "user": serialized_user
        })

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)