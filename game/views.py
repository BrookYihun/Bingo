from django.db.models import Count
import json
from django.utils import timezone
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import permission_classes,api_view
from rest_framework.response import Response
from django.db import models
from django.shortcuts import get_object_or_404

import random

from game.models import Game, UserGameParticipation
from custom_auth.models import User
from game.models import Card

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
    page_size = 10  # Items per page
    page_size_query_param = 'page_size'  # Allow client to override (max 50)
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
    """
    Get top 10 users by total games played (across all games).
    """
    leaderboard = (
        User.objects
        .annotate(total_games=models.Sum('game_participation__times_played'))
        .filter(total_games__isnull=False)
        .order_by('-total_games', 'id')[:10]
    )

    results = []
    for rank, user in enumerate(leaderboard, start=1):
        results.append({
            "rank": rank,
            "user_id": user.id,
            "name": user.name,
            "phone_number": user.phone_number,
            "total_games_played": user.total_games,
        })

    return Response({
        "leaderboard": results,
        "total_users_ranked": len(results)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_games(request):
    """
    Get the 10 most recent closed games (global).
    """
    games = Game.objects.filter(played='closed').order_by('-created_at')[:10]

    recent = []
    for game in games:
        winner_name = "No winner"
        if game.winner:
            try:
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
    """
    Total games won by the authenticated user.
    """
    wins = Game.objects.filter(
        winner=request.user.id,
        played='closed'
    ).count()
    return Response({"total_wins": wins})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_total_games_played(request):
    """
    Total games played by the authenticated user.
    """
    total = request.user.game_participation.aggregate(
        total=models.Sum('times_played')
    )['total'] or 0
    return Response({"total_games_played": total})
