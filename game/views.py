import json
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.core.cache import cache
from django.db import models
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import permission_classes, api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from custom_auth.models import User
from game.models import Card, CustomAuthAbstractuser, CustomAuthUser, TransferLog
from game.models import UserGameParticipation
from .models import Agents, AgentsAccount, PaymentRequest
from .models import DepositAccount
from .models import Game


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_bingo_card(request):
    # Retrieve the card ID(s) from the request parameters
    card_ids = request.GET.getlist('cardId')

    # Validate card IDs to ensure they are all digits
    if not all(card_id.isdigit() for card_id in card_ids):
        return JsonResponse({"error": "Invalid card ID(s)"}, status=400)

    try:
        # Fetch all card objects based on the provided IDs
        cards = Card.objects.filter(id__in=[int(card_id) for card_id in card_ids])

        # Check if the requested cards were found
        if not cards:
            return JsonResponse({"error": "Card(s) not found"}, status=404)

        # Prepare response data for multiple cards
        bingo_table_data = [
            {
                "id": card.id,
                "numbers": json.loads(card.numbers)  # Load JSON field as a Python object
            }
            for card in cards
        ]

        return JsonResponse(bingo_table_data, safe=False)

    except Exception as e:
        # Catch any unexpected errors and return a server error response
        return JsonResponse({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_playing_bingo_card(request):
    game_id = request.GET.get('gameId')

    def flatten_card_ids(card_list):
        """Recursively flatten card IDs to handle any nested lists."""
        flattened = []
        for card in card_list:
            if isinstance(card, list):
                flattened.extend(flatten_card_ids(card))
            else:
                flattened.append(int(card))
        return flattened

    try:
        # Retrieve the specified game
        game = Game.objects.get(id=game_id)


        # Parse playerCard JSON to find cards for the specified user
        players = json.loads(game.playerCard)

        # Find and flatten all card IDs for the specified user
        user_cards = []
        for player in players:
            if player['user'] == int(request.user.id):
                # Flatten card IDs for this player
                user_cards.extend(flatten_card_ids(player['card'] if isinstance(player['card'], list) else [player['card']]))

        # Fetch the Card objects
        cards = Card.objects.filter(id__in=user_cards)

        # Check if any cards were found
        if not cards.exists():
            return JsonResponse({"error": "No cards found for this user in the specified game."}, status=404)

        # Prepare response data for all user cards
        bingo_table_data = [
            {
                "id": card.id,
                "numbers": json.loads(card.numbers)  # Load JSON field format as a Python object
            }
            for card in cards
        ]

        return JsonResponse(bingo_table_data, safe=False)

    except Game.DoesNotExist:
        return JsonResponse({"error": "Game not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@permission_classes([IsAuthenticated])
def generate_random_numbers():
    # Generate a list of numbers from 1 to 75
    numbers = list(range(1, 76))

    # Shuffle the list to randomize the order
    random.shuffle(numbers)

    return numbers

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_games(request):
    now = timezone.now()

    # # Step 1: Get all games with 'Started', 'Created', or 'playing' status
    # active_games_qs = Game.objects.filter(played__in=['Started', 'Created', 'Playing'])

    # # Step 2: Filter games older than 500 seconds
    # expired_games = active_games_qs.filter(started_at__lt=now - timezone.timedelta(seconds=500))

    # # Step 3: Update expired games to 'closed'
    # expired_games.update(played='closed')

    # Step 4: Refresh the queryset to only include valid active games after update
    active_games = (
        Game.objects.filter(played__in=['Started', 'Created'])  # Re-fetch active games
        .values('stake')                                        # Group by stake
        .annotate(count=Count('id'))                            # Count the number in each stake group
    )

    # Convert to dictionary: { stake: count }
    result = {game['stake']: game['count'] for game in active_games}

    return JsonResponse({
        'activeGames': result
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def start_game(request, stake):
    # Get the most recent game for this stake with either 'Started' or 'Created' status
    recent_game = Game.objects.filter(stake=stake, played__in=['Started', 'Created']).order_by('-created_at').first()

    if recent_game:
        if recent_game.played == 'Created':
            # Return the game immediately if it's in 'Created' state
            return JsonResponse({
                'status': 'success',
                'game_id': recent_game.id,
                'message': f'Waiting game found for stake {stake}'
            })
        elif recent_game.played == 'Started':
            # Only return if within 20 seconds
            time_diff = timezone.now() - recent_game.started_at
            if time_diff.total_seconds() <= 20:
                return JsonResponse({
                    'status': 'success',
                    'game_id': recent_game.id,
                    'message': f'Active game found for stake {stake}'
                })

    # No valid recent game found; create a new one
    new_game = Game.objects.create(
        stake=stake,
        numberofplayers=0,
        played='Created',  # Or 'Started' if preferred
        created_at=timezone.now(),
        started_at=timezone.now(),
        total_calls=0,
        random_numbers=json.dumps(generate_random_numbers()),
        winner_price=0,
        admin_cut=0
    )

    return JsonResponse({
        'status': 'success',
        'game_id': new_game.id,
        'message': f'New game created for stake {stake}'
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_game_stat(request, game_id):
    # Retrieve the game instance by ID
    game = get_object_or_404(Game, id=game_id)
    # Retrieve the user instance by ID
    user = get_object_or_404(User, id=request.user.id)

     # Load the existing player card data or initialize as an empty list
    try:
        players = json.loads(game.playerCard) if game.playerCard else []
    except json.JSONDecodeError:
        players = []

    start_delay = 29
    start_time_with_delay = game.started_at + timezone.timedelta(seconds=start_delay)

    # Calculate remaining time until actual game start
    now = timezone.now()
    remaining = (start_time_with_delay - now).total_seconds()
    remaining_seconds = max(int(remaining), 0)  # Make sure it's not negative

    # Prepare the game stats data
    data = {
        "wallet": user.wallet,
        "stake": game.stake,
        "selected_players" : players,
        "game_id": game.id,
        "no_players": game.numberofplayers,
        "bonus": game.bonus,
        "winner": game.winner_price,
        "status": game.played,
        "timer": game.started_at,
        "remaining_seconds": remaining_seconds,
    }

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    # Fetch the user by ID, or return a 404 if not found
    user = get_object_or_404(User, id=request.user.id)

    # Prepare the profile data
    profile_data = {
        "name": user.name,  # Use full name or username
        "phone_number": user.phone_number,  # Check for phone_number attribute
        "balance": user.wallet,  # Default balance to 0.0 if not present
        "bonus": user.bonus,  # Default bonus to 0.0 if not present
    }

    return JsonResponse(profile_data)


from rest_framework.pagination import PageNumberPagination


class GameHistoryPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_game_history(request):
    filter_type = request.GET.get('filter', 'all')

    # Get participations
    participations = request.user.game_participation.select_related('game').order_by('-created_at')

    # Apply filter
    filtered_participations = []
    for part in participations:
        is_winner = (part.game.winner == request.user.id)
        if filter_type == 'wins' and not is_winner:
            continue
        if filter_type == 'losses' and is_winner:
            continue
        filtered_participations.append(part)

    # Paginate
    paginator = GameHistoryPagination()
    paginated_participations = paginator.paginate_queryset(filtered_participations, request)

    # Serialize
    history = []
    for part in paginated_participations:
        game = part.game
        is_winner = (game.winner == request.user.id)
        history.append({
            "game_id": game.id,
            "stake": game.stake,
            "times_played": part.times_played,
            "played_at": part.created_at.isoformat(),
            "winner_price": float(game.winner_price) if game.winner_price else 0,
            "status": game.played,
            "is_winner": is_winner,
        })

    return paginator.get_paginated_response({
        "history": history,
        "filter": filter_type
    })
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_game_participants(request, game_id):
    try:
        game = Game.objects.get(id=game_id)
    except Game.DoesNotExist:
        return Response({"error": "Game not found"}, status=404)

    participants = (
        UserGameParticipation.objects
        .filter(game=game)
        .select_related('user')
        .order_by('created_at')  # Order by join time
    )

    results = []
    for part in participants:
        results.append({
            "user_id": part.user.id,
            "name": part.user.name,
            "phone_number": part.user.phone_number,
            "played_at": part.created_at.isoformat(),
            "is_winner": part.game.winner == part.user.id,
        })

    return Response({
        "game_id": game.id,
        "stake": game.stake,
        "participants": results,
        "total_participants": len(results)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_global_leaderboard(request):
    now = timezone.now()
    current_user = request.user

    # --- Stake filter ---
    stake_param = request.GET.get('stake', '10')
    if stake_param not in ['10', '20', '50', '100']:
        return Response({"error": "Invalid stake."}, status=400)
    selected_stake = stake_param

    def build_leaderboard(start_date, end_date, label):
        """Reusable helper to build leaderboard for a given period."""
        annotated_users = (
            User.objects
            .annotate(
                total_games=Sum(
                    'game_participation__times_played',
                    filter=Q(game_participation__created_at__gte=start_date)
                           & Q(game_participation__created_at__lte=end_date)
                           & Q(game_participation__game__stake=selected_stake),
                )
            )
            .filter(total_games__gt=0)
            .order_by('-total_games', 'id')
        )

        # Build rank map
        all_users_with_rank = list(annotated_users.values('id', 'total_games'))
        user_rank_map = {
            item['id']: {'rank': index + 1, 'total_games_played': item['total_games']}
            for index, item in enumerate(all_users_with_rank)
        }

        # Current user's data
        your_data = user_rank_map.get(current_user.id)
        if your_data:
            your_rank_info = {
                "rank": your_data['rank'],
                "user_id": current_user.id,
                "name": current_user.name,
                "phone_number": current_user.phone_number,
                "total_games_played": your_data['total_games_played']
            }
        else:
            your_rank_info = {
                "rank": None,
                "user_id": current_user.id,
                "name": current_user.name,
                "phone_number": current_user.phone_number,
                "total_games_played": 0
            }

        # Top 10 players
        leaderboard = [
            {
                "rank": user_rank_map[user.id]['rank'],
                "user_id": user.id,
                "name": user.name,
                "phone_number": user.phone_number,
                "total_games_played": user.total_games,
            }
            for user in annotated_users[:10]
        ]

        return {
            "label": label,
            "leaderboard": leaderboard,
            "your_rank": your_rank_info,
            "total_users_ranked": len(user_rank_map),
            "from_date": start_date.date().isoformat(),
            "to_date": end_date.date().isoformat(),
        }

    # --- Daily leaderboard ---
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_data = build_leaderboard(start_of_day, now, "daily")

    # --- Weekly leaderboard (Sunday 00:00 → Saturday 23:59:59) ---
    # Python weekday: Monday=0 ... Saturday=5, Sunday=6
    days_since_sunday = (now.weekday() - 6) % 7
    start_of_week = now - timedelta(days=days_since_sunday)
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    
    weekly_data = build_leaderboard(start_of_week, now, "weekly")

    return Response({
        "daily_leaderboard": daily_data,
        "weekly_leaderboard": weekly_data,
        "filtered_by": {"stake": selected_stake},
        "available_filters": {"stake": ["10", "20", "50", "100"]}
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_games(request):

    games = Game.objects.filter(played='closed').order_by('-created_at')[:10]

    recent = []
    for game in games:
        winner_name = "No winner"
        if game.winner:
            try:
                winner_name = game.winner_name
                if not winner_name:
                    winner_user = User.objects.get(id=game.winner)
                    winner_name = winner_user.name
            except User.DoesNotExist:
                winner_name = "Unknown"
        recent.append({
            "game_id": game.id,
            "stake": game.stake,
            "winner_name": winner_name,
            "Prize": float(game.winner_price),
            "created_at": game.created_at.isoformat(),
            "total_players": game.numberofplayers,
        })
    return Response({"Recent_games": recent})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_total_wins(request):

    wins = Game.objects.filter(
        winner=request.user.id,
        played='closed'
    ).count()
    return Response({"total_wins": wins})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_total_games_played(request):

    total = request.user.game_participation.aggregate(
        total=models.Sum('times_played')
    )['total'] or 0
    return Response({"total_games_played": total})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_total_deposit(request):
    total=PaymentRequest.objects.filter(
        user_id=str(request.user.id),
        payment_type=0,
        payment_status=0,
    ).aggregate(
        total=models.Sum('amount')
    )['total'] or 0

    return Response({"total_deposit": float(total)})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_total_withdrawal(request):

    total = PaymentRequest.objects.filter(
        user_id=str(request.user.id),      # ✅ Convert to string
        payment_type=1,
        payment_status=0,
    ).aggregate(
        total=models.Sum('amount')
    )['total'] or 0

    return Response({"total_withdrawal": float(total)})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_stats(request):

    user_id = request.user.id
    user_id_str = str(user_id)

    # 1. Total Wins
    total_wins = Game.objects.filter(
        winner=user_id,
        played='closed'
    ).count()

    # 2. Total Games Played
    total_games_played = request.user.game_participation.aggregate(
        total=models.Sum('times_played')
    )['total'] or 0

    # 3. Total Deposit (payment_type=0, status=0)
    total_deposit = PaymentRequest.objects.filter(
        user_id=user_id_str,
        payment_type=0,
        payment_status=0
    ).aggregate(total=models.Sum('amount'))['total'] or 0

    # 4. Total Withdrawal (payment_type=1, status=0)
    total_withdrawal = PaymentRequest.objects.filter(
        user_id=user_id_str,
        payment_type=1,
        payment_status=0
    ).aggregate(total=models.Sum('amount'))['total'] or 0

    return Response({
        "total_wins": total_wins,
        "total_games_played": total_games_played,
        "total_deposit": float(total_deposit),
        "total_withdrawal": float(total_withdrawal)
    })

VERIFIER_BASE = "http://88.99.189.198:8001/api/verify/"

ENDPOINTS = {
    0: "verify-telebirr/",
    1: "verify-cbe/",
    3: "verify-cbebirr/",
}

PAYMENT_METHOD_MAPPING = {
    "TELEBIRR": 0,
    "CBE": 1,
    "CBE_BIRR": 3,
}

CACHE_KEY_PREFIX = "deposit_txid:"  # Use colon for better cache key readability
@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def auto_deposit(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    transaction_id = data.get("transaction_id")
    deposit_account_id = data.get("deposit_account_id")

    if not transaction_id or not deposit_account_id:
        return JsonResponse({
            'error': 'Missing required fields: transaction_id or deposit_account_id'
        }, status=400)

    #  Validate and map deposit_account_id to payment_method
    if deposit_account_id not in PAYMENT_METHOD_MAPPING:
        return JsonResponse({
            'error': f'Invalid deposit_account_id: {deposit_account_id}. Must be one of {list(PAYMENT_METHOD_MAPPING.keys())}'
        }, status=400)

    payment_method = PAYMENT_METHOD_MAPPING[deposit_account_id]

    user: CustomAuthAbstractuser = request.user
    if not user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)

    #  Get linked CustomAuthUser
    try:
        custom_user = CustomAuthUser.objects.select_for_update().get(abstractuser_ptr_id=user.id)
    except CustomAuthUser.DoesNotExist:
        return JsonResponse({'error': 'User profile not found.'}, status=500)

    #  CACHE CHECK: Prevent duplicate processing
    cache_key = f"{CACHE_KEY_PREFIX}{transaction_id}"
    if cache.get(cache_key):
        return JsonResponse({
            'error': 'This transaction ID is already being processed or was used recently.'
        }, status=400)
    cache.set(cache_key, True, timeout=300)  # 5-minute lock

    #  DATABASE DUPLICATE CHECK
    if PaymentRequest.objects.filter(transactionsms=transaction_id).exists():
        cache.delete(cache_key)
        return JsonResponse({
            'error': 'This transaction ID has already been used.'
        }, status=400)

    #  Fetch deposit account info
    try:
        deposit_account = DepositAccount.objects.get(deposit_payment_method=deposit_account_id)
    except DepositAccount.DoesNotExist:
        cache.delete(cache_key)
        return JsonResponse({
            'error': f'Deposit account not found for {deposit_account_id}. Contact admin.'
        }, status=500)

    #  Call external verifier API
    api_url = VERIFIER_BASE + ENDPOINTS[payment_method]
    payload = {}

    if payment_method == 0:  # TeleBirr
        payload["receipt_no"] = transaction_id
    elif payment_method == 1:  # CBE
        payload["transaction_id"] = transaction_id
        payload["account_number"] = deposit_account.account_number
    elif payment_method == 3:  # CBE_BIRR
        payload["transaction_id"] = transaction_id
        payload["phone"] = deposit_account.account_number

    try:
        response = requests.post(api_url, json=payload, timeout=15)
    except requests.exceptions.RequestException as e:
        cache.delete(cache_key)
        return JsonResponse({
            'error': f'Verification service unreachable: {str(e)}'
        }, status=500)

    if response.status_code != 200:
        cache.delete(cache_key)
        return JsonResponse({
            'error': 'Verification failed.',
            'details': response.text[:300]
        }, status=response.status_code)

    try:
        full_response = response.json()
    except ValueError:
        cache.delete(cache_key)
        return JsonResponse({
            'error': 'Invalid JSON response from verifier.'
        }, status=500)

    if full_response.get("status") != "success":
        cache.delete(cache_key)
        return JsonResponse({
            'error': 'Transaction verification failed.',
            'reason': full_response.get("detail", "Unknown error")
        }, status=400)

    data_obj = full_response.get("data")
    if not data_obj or not isinstance(data_obj, dict):
        cache.delete(cache_key)
        return JsonResponse({
            'error': 'Missing transaction details in verification response.'
        }, status=500)

    #  Extract amount
    amount_val = data_obj.get("amount")
    try:
        verified_amount = Decimal(str(amount_val))
        if verified_amount <= 0:
            raise InvalidOperation()
    except (InvalidOperation, TypeError, ValueError):
        cache.delete(cache_key)
        return JsonResponse({
            'error': 'Invalid amount received from verifier.'
        }, status=500)

    #  Validate date (< 2 days old)
    date_fields = ["payment_date", "date", "transaction_date"]
    tx_date = None
    for field in date_fields:
        value = data_obj.get(field)
        if value:
            try:
                raw_date = str(value).replace("Z", "+00:00")
                tx_date = datetime.fromisoformat(raw_date)
                break
            except Exception:
                continue

    if tx_date and tx_date < datetime.now(tx_date.tzinfo or datetime.utcnow().tzinfo) - timedelta(days=2):
        cache.delete(cache_key)
        return JsonResponse({
            'error': 'Transaction is older than 2 days and cannot be accepted.'
        }, status=400)

    #  TeleBirr: Validate credited party name
    if payment_method == 0:
        credited_name = str(data_obj.get('credited_party_name', '')).strip().lower()
        expected_name = str(deposit_account.owner_name).strip().lower()
        if credited_name != expected_name:
            cache.delete(cache_key)
            return JsonResponse({
                'error': f'Account name mismatch. Expected "{deposit_account.owner_name}", got "{credited_name}".'
            }, status=400)

    #  ALL CHECKS PASSED: Generate reference_id & Update DB
    now = datetime.now()
    random_part = str(random.randint(1_000_000_000, 9_999_999_999))
    reference_id = f"TXN{now.strftime('%y%m%d')}{now.strftime('%H%M')}{random_part}"

    try:
        # 💰 Update wallet
        custom_user.wallet += verified_amount
        custom_user.no_of_cash_deposited = (custom_user.no_of_cash_deposited or 0) + 1
        custom_user.save(update_fields=['wallet', 'no_of_cash_deposited'])

        # 📝 Save to PaymentRequest
        PaymentRequest.objects.create(
            amount=verified_amount,
            customer_chat_id=getattr(user, 'telegram_id', None),
            customer_phone_number=user.phone_number,
            payment_method=payment_method,
            payment_status=0,  # Accepted
            payment_type=0,    # Deposit
            reference_id=reference_id,
            transactionsms=transaction_id,
            user_id=str(user.id),
            agents_account=None,
            created_at=now,
            updated_at=now
        )

    except Exception as e:
        cache.delete(cache_key)
        return JsonResponse({
            'error': f'Failed to update account or record transaction: {str(e)}'
        }, status=500)

    #  SUCCESS RESPONSE
    return JsonResponse({
        'message': 'Deposit verified and credited successfully.',
        'amount': f'{verified_amount:.2f}',
        'new_balance': f'{custom_user.wallet:.2f}',
        'transaction_id': transaction_id,
        'reference_id': reference_id,
        'currency': 'ETB'
    }, status=200)





@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_deposit_accounts(request):

    try:
        deposit_accounts = DepositAccount.objects.all()

        accounts = []
        for acc in deposit_accounts:
            accounts.append({
                "id": acc.deposit_payment_method,
                "name": acc.deposit_payment_method.replace('_', ' ').title(),
                "account_number": acc.account_number,
                "owner_name": acc.owner_name,

            })

        return JsonResponse({"accounts": accounts}, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch deposit accounts: {str(e)}'}, status=500)


# Payment method mapping
PAYMENT_METHOD_LABELS = {
    0: "TeleBirr",
    1: "CBE",
    3: "CBE Birr",
}

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_online_agent_payment_methods(request):
    try:
        online_agents=Agents.objects.filter(
            is_active=True,
            status=True
        )

        # Extract agent IDs first
        online_agent_ids = online_agents.values_list('id', flat=True)

        # Now use those IDs in the filter
        agent_accounts = AgentsAccount.objects.filter(
            agents_id__in=online_agent_ids,  # ← Use agents_id instead of agents__in
            is_active=True
        ).distinct()

        methods_set=set()
        for account in agent_accounts:
            label=PAYMENT_METHOD_LABELS.get(account.payment_method)
            if label:
                methods_set.add(label)


        payment_methods=sorted(list(methods_set))

        return JsonResponse({"payment_methods": payment_methods}, status=200)

    except Exception as e:
        return JsonResponse({
            'error': f'Failed to fetch online agent payment methods: {str(e)}'
        }, status=500)



PAYMENT_METHOD_ENUM = {
    "TeleBirr": "TELEBIRR",
    "CBE": "CBE",
    "CBE Birr": "CBE_BIRR"
}

PAYMENT_METHOD_LABELS = {
    0: "TeleBirr",
    1: "CBE",
    3: "CBE Birr",
}

BOT_API_URL = "http://localhost/api/v1/agent-bot"


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def withdraw(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    amount_str = data.get("amount")
    bank_name = data.get("bank")  # e.g., "TeleBirr", "CBE"
    account_number = data.get("account_number")

    if not amount_str or not bank_name or not account_number:
        return JsonResponse({
            'error': 'Missing required fields: amount, bank, or account_number'
        }, status=400)

    # --- Validate amount ---
    try:
        amount = Decimal(str(amount_str))
        if amount < Decimal('50'):
            return JsonResponse({
                'error': 'Minimum withdrawal amount is 50 ETB.'
            }, status=400)
    except (InvalidOperation, TypeError):
        return JsonResponse({
            'error': 'Invalid amount format.'
        }, status=400)

    # --- Get authenticated user ---
    user: CustomAuthAbstractuser = request.user
    if not user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)

    # --- Get linked CustomAuthUser profile ---
    try:
        custom_user = CustomAuthUser.objects.select_for_update().get(abstractuser_ptr_id=user.id)
    except CustomAuthUser.DoesNotExist:
        return JsonResponse({'error': 'User profile not found.'}, status=500)

    # --- Check game play count ---
    if custom_user.no_of_games_played is None or custom_user.no_of_games_played < 10:
        return JsonResponse({
            'error': 'You must have played at least 10 games to withdraw.'
        }, status=400)

    # --- Calculate total cost (amount + 3% commission) ---
    commission = amount * Decimal('0.03')
    total_cost = amount + commission

    if custom_user.wallet < total_cost:
        return JsonResponse({
            'error': f'Insufficient balance. You need {total_cost:.2f} ETB (includes 3% commission). Your balance: {custom_user.wallet:.2f} ETB.'
        }, status=400)

    # --- Map bank name to payment method enum for external API ---
    if bank_name not in PAYMENT_METHOD_ENUM:
        return JsonResponse({
            'error': f'Unsupported bank: {bank_name}. Supported: {list(PAYMENT_METHOD_ENUM.keys())}'
        }, status=400)

    payment_method_enum = PAYMENT_METHOD_ENUM[bank_name]  # e.g., "TELEBIRR"

    # --- Find online agents with this payment method ---
    try:
        online_agents = Agents.objects.filter(
            is_active=True,
            status=True
        )
        online_agent_ids = online_agents.values_list('id', flat=True)

        if not online_agent_ids:
            return JsonResponse({
                'error': 'No online agents available right now. Please try again later.'
            }, status=400)

        # Match bank name to internal payment method number
        payment_method_key = None
        for k, v in PAYMENT_METHOD_LABELS.items():
            if v == bank_name:
                payment_method_key = k
                break

        if payment_method_key is None:
            return JsonResponse({
                'error': f'Internal error: Unknown payment method "{bank_name}"'
            }, status=500)

        agent_accounts = AgentsAccount.objects.filter(
            agents_id__in=list(online_agent_ids),
            is_active=True,
            payment_method=payment_method_key
        ).select_related('agents')

        if not agent_accounts.exists():
            return JsonResponse({
                'error': f'No online agent currently supports {bank_name}.'
            }, status=400)

        # Randomly select one agent account
        selected_account = random.choice(list(agent_accounts))
        agent = selected_account.agents

        if not agent.chat_id:
            return JsonResponse({
                'error': 'Selected agent does not have a chat ID. Please try again.'
            }, status=400)

    except Exception as e:
        return JsonResponse({
            'error': f'Failed to find suitable agent: {str(e)}'
        }, status=500)

    # --- Generate reference ID ---
    reference_id = str(uuid.uuid4())

    # --- Prepare payload for external bot API ---
    payload = {
        "referenceId": reference_id,
        "chatId": int(agent.chat_id),
        "customerPhoneNumber": account_number,
        "amount": float(amount),
        "paymentMethod": payment_method_enum,
        "paymentType": "WITHDRAWAL",
        "transactionMessage": None
    }

    # --- Call external bot API (fire-and-forget) ---
    bot_sent = False
    bot_error_msg = None

    try:
        response = requests.post(BOT_API_URL, json=payload, timeout=15)

        if 200 <= response.status_code < 300:
            bot_sent = True
        else:
            bot_error_msg = f"Unexpected status {response.status_code}: {response.text[:300]}"
    except requests.exceptions.RequestException as e:
        bot_error_msg = f"Request failed: {str(e)}"
    except Exception as e:
        bot_error_msg = f"Unknown error: {str(e)}"

    if not bot_sent:
        print(f"[Warning] Could not deliver to agent bot: {bot_error_msg}")
    else:
        print("[Bot API] Successfully delivered withdrawal request.")

    # --- RESERVE FUNDS: Deduct from wallet, add to reserved_amount ---
    try:
        # Deduct full amount (including commission) from wallet
        custom_user.wallet -= total_cost

        # Add to reserved_amount (safe until confirmed/refunded)
        custom_user.reserved_amount = (custom_user.reserved_amount or Decimal('0')) + total_cost

        # Save both fields
        custom_user.save(update_fields=['wallet', 'reserved_amount'])

    except Exception as e:
        return JsonResponse({
            'error': f'Failed to reserve funds: {str(e)}'
        }, status=500)

    # --- Save to PaymentRequest (status=1 → pending, type=1 → withdrawal) ---
    try:
        PaymentRequest.objects.create(
            amount=amount,
            customer_chat_id=user.telegram_id,
            customer_phone_number=account_number,
            payment_method=payment_method_key,
            payment_status=1,  # Pending
            payment_type=1,    # Withdrawal
            reference_id=reference_id,
            transactionsms=None,
            user_id=str(user.id),
            agents_account=selected_account,
            created_at=timezone.now(),
            updated_at=timezone.now()
        )
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to save withdrawal request: {str(e)}'
        }, status=500)

    # --- SUCCESS RESPONSE ---
    return JsonResponse({
        'message': 'Withdrawal request submitted successfully.',
        'amount': f'{amount:.2f}',
        'commission': f'{commission:.2f}',
        'total_deducted': f'{total_cost:.2f}',
        'new_balance': f'{custom_user.wallet:.2f}',
        'reserved_amount': f'{custom_user.reserved_amount:.2f}',
        'reference_id': reference_id,
        'currency': 'ETB',
        'agent_name': agent.name or "Unknown Agent",
        'agent_phone': agent.phone_number or "",
        'bank': bank_name,
        'account_number': account_number
    }, status=200)




def normalize_phone(phone: str) -> list:
    """
    Returns a list of possible normalized phone number formats for matching.
    Handles Ethiopian numbers in various forms:
        - 0987654321
        - +251987654321
        - 251987654321
        - 987654321
    """
    if not phone:
        return []

    clean = ''.join(filter(str.isdigit, phone))
    candidates = set()

    if len(clean) == 10 and clean.startswith('0'):
        no_zero = clean[1:]
        candidates.add(f"+251{no_zero}")
        candidates.add(no_zero)
        candidates.add(clean)
    elif len(clean) == 9:
        with_zero = f"0{clean}"
        with_plus = f"+251{clean}"
        candidates.add(with_zero)
        candidates.add(with_plus)
        candidates.add(clean)
    elif len(clean) == 12 and clean.startswith('251'):
        candidates.add(f"+{clean}")
    elif len(clean) == 13 and clean.startswith('+251'):
        candidates.add(clean)
    elif len(clean) == 10:  # e.g., 98xxxxxxx but 10 digits
        candidates.add(f"+251{clean[1:]}" if clean.startswith('0') else f"+251{clean}")

    candidates.discard("")
    return list(candidates)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def transfer(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    amount_str = data.get("amount")
    to_phone = data.get("to_phone")

    if not amount_str or not to_phone:
        return JsonResponse({
            'error': 'Missing required fields: amount or to_phone'
        }, status=400)

    # --- Validate amount ---
    try:
        amount = Decimal(str(amount_str))
        if amount <= 0:
            return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)
    except (InvalidOperation, TypeError):
        return JsonResponse({'error': 'Invalid amount format.'}, status=400)

    # --- Get authenticated user (sender) ---
    sender: CustomAuthAbstractuser = request.user
    if not sender.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)

    # --- Get sender's CustomAuthUser profile ---
    try:
        sender_profile = CustomAuthUser.objects.select_for_update().get(abstractuser_ptr_id=sender.id)
    except CustomAuthUser.DoesNotExist:
        return JsonResponse({'error': 'Sender profile not found.'}, status=500)

    # --- Check balance ---
    if sender_profile.wallet < amount:
        return JsonResponse({
            'error': f'Insufficient balance. You have {sender_profile.wallet:.2f} ETB, need {amount:.2f} ETB.'
        }, status=400)

    # --- Normalize recipient phone and find candidate numbers ---
    phone_candidates = normalize_phone(to_phone)
    if not phone_candidates:
        return JsonResponse({'error': 'Invalid phone number format.'}, status=400)

    # --- Find recipient AbstractUser ---
    recipient_abstract = None
    for candidate in phone_candidates:
        try:
            recipient_abstract = CustomAuthAbstractuser.objects.get(phone_number=candidate)
            break
        except CustomAuthAbstractuser.DoesNotExist:
            continue

    if not recipient_abstract:
        return JsonResponse({
            'error': f'Recipient not found for any format of "{to_phone}". Tried: {phone_candidates}'
        }, status=404)

    # --- Get recipient's CustomAuthUser profile ---
    try:
        recipient_profile = CustomAuthUser.objects.get(abstractuser_ptr_id=recipient_abstract.id)
    except CustomAuthUser.DoesNotExist:
        return JsonResponse({'error': 'Recipient profile not found.'}, status=500)

    # --- Can't send to self ---
    if sender.id == recipient_abstract.id:
        return JsonResponse({
            'error': 'You cannot transfer money to yourself.'
        }, status=400)

    # --- Perform transfer ---
    try:
        # Deduct from sender
        sender_profile.wallet -= amount
        sender_profile.save(update_fields=['wallet'])

        # Add to recipient
        recipient_profile.wallet += amount
        recipient_profile.save(update_fields=['wallet'])

        # Log transfer
        TransferLog.objects.create(
            from_user_id=sender.id,
            to_user_id=recipient_abstract.id,
            amount=amount,
            created_at=timezone.now()
        )

    except Exception as e:
        return JsonResponse({
            'error': f'Transfer failed: {str(e)}'
        }, status=500)

    # --- Success response ---
    return JsonResponse({
        'message': 'Transfer completed successfully.',
        'amount': f'{amount:.2f}',
        'from': sender.phone_number,
        'to': recipient_abstract.phone_number,
        'recipient_name': recipient_abstract.name,
        'new_balance': f'{sender_profile.wallet:.2f}',
        'currency': 'ETB'
    }, status=200)
def get_paginated_data(data, page=None, limit=None):

    try:
        page = max(1, int(page or 1))
        limit = max(1, min(int(limit or 10), 100))  # Max 100 per page
    except (ValueError, TypeError):
        page, limit = 1, 10

    start = (page - 1) * limit
    end = start + limit
    total = len(data)

    paginated = data[start:end]
    has_more = end < total

    return paginated, has_more, total
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_history(request):
    user = request.user

    try:
        # Fetch payment requests for this user
        payments = PaymentRequest.objects.filter(user_id=str(user.id)).order_by('-created_at')

        result = []
        for p in payments:
            # Map payment_type: 0=Deposit, 1=Withdrawal
            if p.payment_type == 0:
                tx_type = "Deposit"
            elif p.payment_type == 1:
                tx_type = "Withdrawal"
            else:
                tx_type = "Unknown"

            # Map payment_status: 0=Accepted, 1=Pending
            status = "Success" if p.payment_status == 0 else "Pending" if p.payment_status == 1 else "Failed"

            result.append({
                "reference_id": p.reference_id,
                "transaction_id": p.transactionsms,  # Only for deposits
                "type": tx_type,
                "status": status,
                "amount": f'{p.amount:.2f}' if p.amount else '0.00',
                "method": {
                    0: "TeleBirr",
                    1: "CBE",
                    3: "CBE Birr"
                }.get(p.payment_method, "Unknown"),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })

        # --- Pagination ---
        page = request.GET.get('page')
        limit = request.GET.get('limit')

        paginated_items, has_more, total = get_paginated_data(result, page, limit)

        return JsonResponse({
            "page": int(page or 1) if page is not None else 1,
            "limit": int(limit or 10),
            "total": total,
            "has_more": has_more,
            "transactions": paginated_items
        }, status=200)

    except Exception as e:
        return JsonResponse({
            'error': f'Failed to load transaction history: {str(e)}'
        }, status=500)

from django.db import connection  # ← For safe raw queries (to avoid game_customauthuser issue)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transfer_history(request):
    user = request.user

    try:
        # Get user's abstract ID
        user_abstract_id = user.id

        result = []

        # --- Fetch Sent Transfers ---
        sent_transfers = TransferLog.objects.filter(from_user_id=user_abstract_id)
        for t in sent_transfers:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT u.phone_number, u.name 
                        FROM custom_auth_abstractuser u
                        WHERE u.id = %s
                    """, [t.to_user_id])
                    row = cursor.fetchone()
                    if row:
                        to_phone, to_name = row
                    else:
                        to_phone, to_name = "Unknown", "Unknown"
            except:
                to_phone, to_name = "Unknown", "Unknown"

            result.append({
                "direction": "Sent",
                "to": to_phone,
                "to_name": to_name,
                "amount": f'{t.amount:.2f}',
                "created_at": t.created_at.isoformat(),
            })

        # --- Fetch Received Transfers ---
        received_transfers = TransferLog.objects.filter(to_user_id=user_abstract_id)
        for t in received_transfers:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT u.phone_number, u.name 
                        FROM custom_auth_abstractuser u
                        WHERE u.id = %s
                    """, [t.from_user_id])
                    row = cursor.fetchone()
                    if row:
                        from_phone, from_name = row
                    else:
                        from_phone, from_name = "Unknown", "Unknown"
            except:
                from_phone, from_name = "Unknown", "Unknown"

            result.append({
                "direction": "Received",
                "from": from_phone,
                "from_name": from_name,
                "amount": f'{t.amount:.2f}',
                "created_at": t.created_at.isoformat(),
            })

        # Sort by date (newest first)
        result.sort(key=lambda x: x['created_at'], reverse=True)

        # --- Pagination ---
        page = request.GET.get('page')
        limit = request.GET.get('limit')

        paginated_items, has_more, total = get_paginated_data(result, page, limit)

        return JsonResponse({
            "page": int(page or 1) if page is not None else 1,
            "limit": int(limit or 10),
            "total": total,
            "has_more": has_more,
            "transfers": paginated_items
        }, status=200)

    except Exception as e:
        return JsonResponse({
            'error': f'Failed to load transfer history: {str(e)}'
        }, status=500)