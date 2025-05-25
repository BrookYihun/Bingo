# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import Group
from .serializer import GroupSerializer
from django.utils.crypto import get_random_string
from django.contrib.auth import get_user_model

User = get_user_model()

class GroupCreateUpdateView(APIView):
    def post(self, request):
        data = request.data.copy()

        # Get user from token/session
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

        # Generate unique group link
        if not data.get('group_link'):
            data['group_link'] = get_random_string(16)

        # Set the owner as the authenticated user
        data['owner'] = user.id

        serializer = GroupSerializer(data=data)
        if serializer.is_valid():
            group = serializer.save()
            group.subscribers.add(user)  # Auto-subscribe creator
            return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_groups(request):
    user = request.user
    groups = Group.objects.filter(subscribers=user)
    serializer = GroupSerializer(groups, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def public_groups(request):
    groups = Group.objects.filter(is_public=True)
    serializer = GroupSerializer(groups, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def private_groups(request):
    user = request.user
    groups = Group.objects.filter(is_public=False, subscribers=user)
    serializer = GroupSerializer(groups, many=True)
    return Response(serializer.data)
