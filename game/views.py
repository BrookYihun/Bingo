from django.db.models import Count
import json
from django.utils import timezone
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes,api_view
from rest_framework.response import Response

from django.shortcuts import get_object_or_404

import random

from game.models import Game
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
    user_id = request.GET.get('userId')
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
            if player['user'] == int(user_id):
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
    # Query to count active games by stake where the game status is 'Started'
    active_games = (
        Game.objects.filter(played='Started')  # Filter by games that are started
        .values('stake')                       # Group by stake
        .annotate(count=Count('id'))           # Count the number of games in each stake group
    )

    # Convert the result into a dictionary where the keys are stake values and the values are the counts
    result = {game['stake']: game['count'] for game in active_games}

    return JsonResponse({
        'activeGames': result
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def start_game(request, stake):
    # Check if there is an active game with the chosen stake
    active_game = Game.objects.filter(stake=stake, played='Started').order_by('-created_at').first()
    
    if active_game:
        # Return the ID of the last active game if found
        return JsonResponse({
            'status': 'success',
            'game_id': active_game.id,
            'message': f'Active game found for stake {stake}'
        })
    
    # If no active game is found, create a new game
    new_game = Game.objects.create(
        stake=stake,
        numberofplayers=0,  # Adjust based on your initial setup
        played='Started',
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
def get_game_stat(request, game_id, user_id):
    # Retrieve the game instance by ID
    game = get_object_or_404(Game, id=game_id)
    # Retrieve the user instance by ID
    user = get_object_or_404(User, id=user_id)

     # Load the existing player card data or initialize as an empty list
    try:
        players = json.loads(game.playerCard) if game.playerCard else []
    except json.JSONDecodeError:
        players = []

    # Prepare the game stats data
    data = {
        "wallet": user.wallet,
        "stake": game.stake,
        "selected_players" : players,
        "game_id": game.id,
        "no_players": game.numberofplayers,
        "bonus": game.bonus,
        "winner": game.winner_price,
        "status": game.played
    }

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_profile(request,user_id):
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
