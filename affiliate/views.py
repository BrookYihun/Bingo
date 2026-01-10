from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from custom_auth.models import User
from custom_auth.serializer import UserSerializer
from game.models import PaymentRequest
from .models import AffiliateWithdrawRequest
import uuid

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class AffiliateReferralsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Check if the user is an affiliate
        if not getattr(user, 'is_affiliate', False):
             return Response(
                 {"error": "User is not an affiliate."}, 
                 status=status.HTTP_403_FORBIDDEN
             )

        # The affiliate's telegram_id is used as the reference key
        telegram_id = user.telegram_id
        
        if not telegram_id:
             return Response(
                 {"error": "Affiliate does not have a Telegram ID set."}, 
                 status=status.HTTP_400_BAD_REQUEST
             )

        # Find users who registered with this affiliate's telegram_id as reference
        referrals = User.objects.filter(reference=telegram_id).order_by('-date_joined')
        
        # Simple search filter
        search_query = request.query_params.get('search')
        if search_query:
            referrals = referrals.filter(name__icontains=search_query)

        # Pagination
        paginator = StandardResultsSetPagination()
        page_referrals = paginator.paginate_queryset(referrals, request)
        
        # Get ids of referred users (on this page)
        referral_ids = [str(user.id) for user in page_referrals]

        # Fetch successful cash deposits for these users
        # payment_status=1 means completed/approved
        # payment_type=0 means deposit (according to requirements)
        deposits = PaymentRequest.objects.filter(
            user_id__in=referral_ids,
            payment_status=1,
            payment_type=0
        ).order_by('-created_at')

        # Group deposits by user_id
        deposits_by_user = {}
        total_deposits_by_user = {}

        for deposit in deposits:
            uid = deposit.user_id
            if uid not in deposits_by_user:
                deposits_by_user[uid] = []
                total_deposits_by_user[uid] = 0.0
            
            deposits_by_user[uid].append({
                "id": deposit.id,
                "amount": deposit.amount,
                "created_at": deposit.created_at,
                "payment_type": deposit.payment_type,
            })
            # Add to total
            total_deposits_by_user[uid] += float(deposit.amount or 0)

        serializer = UserSerializer(page_referrals, many=True)
        serialized_data = serializer.data

        # Attach deposit history to each user in the response
        for user_data in serialized_data:
            # serializer.data['id'] is typically an integer, match with stored string id
            uid = str(user_data.get('id')) 
            user_data['deposit_history'] = deposits_by_user.get(uid, [])
            user_data['total_deposited'] = total_deposits_by_user.get(uid, 0.0)

        # Return paginated response
        # We can include extra meta data if really needed, but get_paginated_response is standard
        return paginator.get_paginated_response(serialized_data)


class AffiliateTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Check if the user is an affiliate
        if not getattr(user, 'is_affiliate', False):
             return Response(
                 {"error": "User is not an affiliate."}, 
                 status=status.HTTP_403_FORBIDDEN
             )

        telegram_id = user.telegram_id
        if not telegram_id:
             return Response(
                 {"error": "Affiliate does not have a Telegram ID set."}, 
                 status=status.HTTP_400_BAD_REQUEST
             )

        # 1. Get list of users (id) referred by the affiliate
        referrals = User.objects.filter(reference=telegram_id)
        referral_ids = [str(u.id) for u in referrals]

        # 2. List of payment request that are successful, deposit, user id in (1) + sort by date desc
        transactions = PaymentRequest.objects.filter(
            user_id__in=referral_ids,
            payment_status=1,
            payment_type=0
        ).order_by('-created_at')

        # Filter by Date
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            transactions = transactions.filter(created_at__gte=start_date)
        if end_date:
            transactions = transactions.filter(created_at__lte=end_date)

        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(transactions, request)

        # Serialize transactions manually (or use a serializer if available)
        data = []
        for t in result_page:
            data.append({
                "id": t.id,
                "amount": t.amount,
                "created_at": t.created_at,
                "user_id": t.user_id,
                "payment_type": t.payment_type,
                "payment_status": t.payment_status
            })

        return paginator.get_paginated_response(data)

class AffiliateWithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        
        # Check if the user is an affiliate
        if not getattr(user, 'is_affiliate', False):
             return Response({"error": "User is not an affiliate."}, status=status.HTTP_403_FORBIDDEN)

        amount = request.data.get('amount')
        bank_name = request.data.get('bank_name')
        account_number = request.data.get('account_number')

        if not amount or not bank_name or not account_number:
            return Response({"error": "Amount, bank name, and account number are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
        except ValueError:
             return Response({"error": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
        
        if amount <= 0:
            return Response({"error": "Amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

        # Check balance
        # Only check against the affiliate_wallet as per requirements
        # request.user is AbstractUser, we need to access the child User model
        try:
             affiliate_user = user.user
        except User.DoesNotExist:
             return Response({"error": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if affiliate_user.affiliate_wallet < amount:
            return Response({"error": "Insufficient affiliate balance."}, status=status.HTTP_400_BAD_REQUEST)

        # Create Withdrawal Request
        reference = str(uuid.uuid4())[:8].upper() # Generate a short unique ref
        
        withdrawal = AffiliateWithdrawRequest.objects.create(
            user=affiliate_user,
            amount=amount,
            bank_name=bank_name,
            account_number=account_number,
            reference_number=reference,
            status=0 # Pending
        )

        return Response({
            "message": "Withdrawal request created successfully.",
            "reference": reference,
            "remaining_balance": affiliate_user.affiliate_wallet
        }, status=status.HTTP_201_CREATED)




class AffiliateWithdrawHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not getattr(user, 'is_affiliate', False):
             return Response({"error": "User is not an affiliate."}, status=status.HTTP_403_FORBIDDEN)
        
        try:
             affiliate_user = user.user
        except User.DoesNotExist:
             return Response({"error": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)

        status_param = request.query_params.get('status')
        
        withdrawals = AffiliateWithdrawRequest.objects.filter(user=affiliate_user).order_by('-created_at')
        
        if status_param is not None:
             # Map string status to integer for filtering
             status_map = {
                 'pending': 0,
                 'accepted': 1,
                 'rejected': 2
             }
             if status_param.lower() in status_map:
                 withdrawals = withdrawals.filter(status=status_map[status_param.lower()])
             else:
                 try:
                     withdrawals = withdrawals.filter(status=int(status_param))
                 except ValueError:
                     pass

        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(withdrawals, request)
        
        # Map integer status to string for response
        status_display_map = {
            0: 'pending',
            1: 'accepted',
            2: 'rejected'
        }

        data = []
        for w in result_page:
            data.append({
                "id": w.id,
                "amount": w.amount,
                "bank_name": w.bank_name,
                "account_number": w.account_number,
                "reference_number": w.reference_number,
                "status": status_display_map.get(w.status, 'unknown'),
                "created_at": w.created_at,
                "updated_at": w.updated_at
            })

        return paginator.get_paginated_response(data)
