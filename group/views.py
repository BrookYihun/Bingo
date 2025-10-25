# views.py
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils.timezone import make_aware
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Group
from .models import GroupWithdrawRequest
from .serializer import GroupSerializer, OwnerGroupDashboardSerializer, GroupWithdrawRequestSerializer

User = get_user_model()

class GroupCreateUpdateView(APIView):
    def post(self, request):
        data = request.data.copy()
        user = request.user

        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

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

    def get(self, request, group_id=None):
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

        if not group_id:
            return Response({'error': 'Group ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        group = get_object_or_404(Group, id=group_id)

        if group.owner != user and user not in group.subscribers.all():
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        return Response(GroupSerializer(group).data, status=status.HTTP_200_OK)

    def delete(self, request, group_id=None):
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

        if not group_id:
            return Response({'error': 'Group ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        group = get_object_or_404(Group, id=group_id)

        if group.owner != user:
            return Response({'error': 'Only the group owner can delete this group'}, status=status.HTTP_403_FORBIDDEN)

        group.is_active = False
        group.save()
        return Response({'message': 'Group deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
    
@api_view(["POST"])
@permission_classes([AllowAny])
def subscribe_via_referral(request):
    """
    Accepts: {
    "telegram_id": "123456789",
    "referral_code": "PR000001"
    }
    """
    telegram_id = request.data.get("telegram_id")
    referral_code = request.data.get("referral_code")

    if not telegram_id or not referral_code:
        return Response({"detail": "telegram_id and referral_code required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return Response({"detail": "User with given telegram_id not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        group = Group.objects.get(referral_code=referral_code, is_active=True)
    except Group.DoesNotExist:
        return Response({"detail": "Invalid or inactive referral code"}, status=status.HTTP_404_NOT_FOUND)

    group.subscribers.add(user)
    return Response({"detail": f"{user.name} subscribed to {group.name}"}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_groups(request):
    user = request.user
    groups = Group.objects.filter(subscribers=user, is_active=True)
    serializer = GroupSerializer(groups, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def public_groups(request):
    groups = Group.objects.filter(is_public=True, is_active=True)
    serializer = GroupSerializer(groups, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def private_groups(request):
    user = request.user
    groups = Group.objects.filter(is_public=False, subscribers=user, is_active=True)
    serializer = GroupSerializer(groups, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscribe_to_group(request):
    group_id = request.data.get("group_id")
    if not group_id:
        return Response({"detail": "Missing group_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        group = Group.objects.get(id=group_id, is_active=True)
        group.subscribers.add(request.user)
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
        group = Group.objects.get(id=group_id, is_active=True)
        group.subscribers.remove(request.user)
        return Response({"detail": "Unsubscribed from group"}, status=status.HTTP_200_OK)
    except Group.DoesNotExist:
        return Response({"detail": "Group not found"}, status=status.HTTP_404_NOT_FOUND)



class OwnerDashboardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def owner_dashboard(request):


    base_queryset = Group.objects.filter(owner=request.user, is_active=True)

    total_earnings = base_queryset.aggregate(
        total=Sum('group_wallet')
    )['total'] or 0
    groups = base_queryset.annotate(
        subscribers_count=Count('subscribers')
    )

    #  FILTERING
    is_public = request.query_params.get('is_public')
    if is_public is not None:
        groups = groups.filter(is_public=is_public.lower() == 'true')

    search = request.query_params.get('search')
    if search:
        groups = groups.filter(Q(name__icontains=search) | Q(description__icontains=search))

    # SORTING
    ordering = request.query_params.get('ordering', '-created_at')
    valid_fields = {
        'created_at', '-created_at',
        'group_wallet', '-group_wallet',
        'subscribers_count', '-subscribers_count',
        'name', '-name'
    }
    if ordering in valid_fields:
        groups = groups.order_by(ordering)
    else:
        groups = groups.order_by('-created_at')

    # PREFETCH RECENT GAMES (last 5 closed per group)
    group_ids = list(groups.values_list('id', flat=True))
    recent_games_map = {}
    if group_ids:
        from game.models import Game
        recent_games = Game.objects.filter(
            group_game__group_id__in=group_ids,
            played='closed'
        ).order_by('-started_at')

        for game in recent_games:
            gid = game.group_game.group_id
            if gid not in recent_games_map:
                recent_games_map[gid] = []
            if len(recent_games_map[gid]) < 5:
                recent_games_map[gid].append(game)

    groups_list = list(groups)
    for group in groups_list:
        group.recent_games = recent_games_map.get(group.id, [])

    # === PAGINATION ===
    paginator = OwnerDashboardPagination()
    paginated_groups = paginator.paginate_queryset(groups_list, request)

    # === SERIALIZATION ===
    serializer = OwnerGroupDashboardSerializer(paginated_groups, many=True)

    return paginator.get_paginated_response({
        'owner_id': request.user.id,
        'total_active_groups': Group.objects.filter(owner=request.user, is_active=True).count(),
         'total_earnings': float(total_earnings),
        'groups': serializer.data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_group_withdrawal(request):
    group_id = request.data.get('group_id')
    amount = request.data.get('amount')

    if not group_id or not amount:
        return Response(
            {"detail": "Both 'group_id' and 'amount' are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        amount = Decimal(str(amount))
        if amount <= 0:
            return Response(
                {"detail": "Amount must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST
            )
    except (ValueError, TypeError):
        return Response(
            {"detail": "Invalid amount format."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Use a database transaction with row-level locking
    try:
        with transaction.atomic():
            # Lock the Group row for update to prevent concurrent modifications
            group = Group.objects.select_for_update().get(
                id=group_id,
                is_active=True
            )

            # Ensure the logged-in user is the owner
            if group.owner != request.user:
                return Response(
                    {"detail": "You are not the owner of this group."},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Check balance under lock
            if group.group_wallet < amount:
                return Response(
                    {"detail": "Insufficient funds in group wallet."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create the withdrawal request (status defaults to PENDING)
            withdraw_request = GroupWithdrawRequest.objects.create(
                group=group,
                owner=request.user,
                amount=amount
            )



    except Group.DoesNotExist:
        return Response(
            {"detail": "Group not found or inactive."},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response({
        "detail": "Withdrawal request submitted successfully.",
        "reference_id": withdraw_request.reference_id,
        "amount": str(withdraw_request.amount),
        "status": withdraw_request.get_payment_status_display()
    }, status=status.HTTP_201_CREATED)


class WithdrawalHistoryPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def withdrawal_history(request):

    withdrawals = GroupWithdrawRequest.objects.filter(
        owner=request.user
    ).select_related('group').order_by('-created_at')

    # === Filter by status ===
    status_filter = request.query_params.get('status')
    if status_filter in ['0', '1', '2']:
        withdrawals = withdrawals.filter(payment_status=status_filter)

    # === Filter by date range ===
    from_date_str = request.query_params.get('from_date')
    to_date_str = request.query_params.get('to_date')

    if from_date_str or to_date_str:
        try:
            # Parse and validate dates
            from_date = None
            to_date = None

            if from_date_str:
                from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
                from_date = make_aware(datetime.combine(from_date, datetime.min.time()))

            if to_date_str:
                to_date = datetime.strptime(to_date_str, "%Y-%m-%d")
                to_date = make_aware(datetime.combine(to_date, datetime.max.time().replace(microsecond=0)))

            # Apply filters
            if from_date:
                withdrawals = withdrawals.filter(created_at__gte=from_date)
            if to_date:
                withdrawals = withdrawals.filter(created_at__lte=to_date)

        except (ValueError, TypeError, OverflowError):
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=400
            )

    paginator = WithdrawalHistoryPagination()
    paginated_withdrawals = paginator.paginate_queryset(withdrawals, request)
    serializer = GroupWithdrawRequestSerializer(paginated_withdrawals, many=True)

    return paginator.get_paginated_response(serializer.data)