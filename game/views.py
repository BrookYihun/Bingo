from itertools import count
import json
from django.utils import timezone
from django.http import JsonResponse

import random

from game.models import Game

def get_bingo_card(request):
    from game.models import Card
    cardnumber = request.GET.get('paramName', '')
    card = Card.objects.get(id=int(cardnumber))
    card_numbers = json.loads(card.numbers)
    bingo_table_json = json.dumps(card_numbers)
    return JsonResponse(bingo_table_json,safe=False)


def generate_random_numbers():
    # Generate a list of numbers from 1 to 75
    numbers = list(range(1, 76))
    
    # Shuffle the list to randomize the order
    random.shuffle(numbers)
    
    return numbers

def get_active_games(request):
    # Query to count active games by stake where the game status is 'Started'
    active_games = (
        Game.objects.filter(played='Started')  # Filter by games that are started
        .values('stake')                       # Group by stake
        .annotate(count=count('id'))           # Count the number of games in each stake group
    )

    # Convert the result into a dictionary where the keys are stake values and the values are the counts
    result = {game['stake']: game['count'] for game in active_games}

    return JsonResponse({
        'activeGames': result
    })

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
        winner_price=0,
        admin_cut=0
    )
    
    return JsonResponse({
        'status': 'success',
        'game_id': new_game.id,
        'message': f'New game created for stake {stake}'
    })

