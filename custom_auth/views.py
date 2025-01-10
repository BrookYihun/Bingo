import base64
import datetime
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import RefreshToken
from .serializer import UserSerializer  # Make sure you have a serializer for User model
import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore
from rest_framework.decorators import api_view
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework.exceptions import ValidationError


# Function to generate JWT tokens and session ID
def get_tokens_for_user(user_id, request=None):
    # Generate JWT tokens
    user = user = get_object_or_404(User, id=user_id)
    if(user):
        refresh = RefreshToken.for_user(user)

        # Create a session for the user if it doesn't exist
        if request and not request.session.session_key:
            login(request, user)  # Log the user in and create a session
        else:
            # Manually create a session if no request is passed
            session = SessionStore()
            session['user_id'] = user.id  # Store user-specific data in the session
            session.create()
            session_key = session.session_key
        
        session_key = request.session.session_key if request else session.session_key

        # Return tokens and session ID
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'sessionid': session_key,
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

# Login view
@permission_classes([AllowAny])
class LoginView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        password = request.data.get('password')

        # Authenticate the user
        user = authenticate(phone_number=phone_number, password=password)
        if user:
            if not user.is_verified:
                return Response(
                    {"error": "Not Verified User! Verify"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Generate tokens and session ID
            tokens = get_tokens_for_user(user.id, request)
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

@api_view(['GET'])
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

@api_view(['GET'])
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
def verify_token(request):
    try:
        # Retrieve tokens from the request
        access_token = request.GET.get('access', None)
        refresh_token = request.GET.get('refresh', None)
        session_id = request.GET.get('sessionid', None)

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

        # Validate Session ID
        if session_id:
            try:
                session = Session.objects.get(session_key=session_id)
                session_data = session.get_decoded()
                if 'user_id' not in session_data:
                    return Response({"error": "Invalid session"}, status=403)
            except Session.DoesNotExist:
                return Response({"error": "Invalid or expired session ID"}, status=403)
        else:
            return Response({"error": "Session ID missing"}, status=403)

        # All tokens are valid
        return Response({"message": "All tokens are valid"}, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=400)

@api_view(['GET']) 
@permission_classes([AllowAny])   
def telegram_login(request):
    session_key = request.GET.get('session_key')
    if not session_key:
        return Response({'error': 'No session key provided'}, status=400)

    try:
        session = Session.objects.get(session_key=session_key)
        session_data = session.get_decoded()
        user_id = session_data.get('_auth_user_id')
        user = User.objects.get(id=user_id)
        login(request, user)
        return Response({'message': 'User authenticated successfully'}, status=200)
    except Exception as e:
        return Response({'error': str(e)}, status=500)