# views.py
from django.shortcuts import get_object_or_404
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
        user = request.user

        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

        if not data.get('group_link'):
            from django.utils.crypto import get_random_string
            data['group_link'] = get_random_string(16)

        data['owner'] = user.id

        serializer = GroupSerializer(data=data)
        if serializer.is_valid():
            group = serializer.save()
            group.subscribers.add(user)
            return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

        group_id = request.data.get('id')
        if not group_id:
            return Response({'error': 'Group ID is required for editing'}, status=status.HTTP_400_BAD_REQUEST)

        group = get_object_or_404(Group, id=group_id)

        if group.owner != user:
            return Response({'error': 'Only the group owner can edit this group'}, status=status.HTTP_403_FORBIDDEN)

        serializer = GroupSerializer(group, data=request.data, partial=True)
        if serializer.is_valid():
            updated_group = serializer.save()
            return Response(GroupSerializer(updated_group).data, status=status.HTTP_200_OK)
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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscribe_to_group(request):
    group_id = request.data.get("group_id")
    if not group_id:
        return Response({"detail": "Missing group_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        group = Group.objects.get(id=group_id)
        group.members.add(request.user)
        return Response({"detail": "Subscribed to group"}, status=status.HTTP_200_OK)
    except Group.DoesNotExist:
        return Response({"detail": "Group not found"}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unsubscribe_from_group(request):
    group_id = request.data.get("group_id")
    if not group_id:
        return Response({"detail": "Missing group_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        group = Group.objects.get(id=group_id)
        group.members.remove(request.user)
        return Response({"detail": "Unsubscribed from group"}, status=status.HTTP_200_OK)
    except Group.DoesNotExist:
        return Response({"detail": "Group not found"}, status=status.HTTP_404_NOT_FOUND)
