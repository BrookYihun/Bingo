import json
import threading
import time
from django.utils import timezone
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

active_games = {}

class GameConsumer(WebsocketConsumer):
    game_random_numbers = []
    called_numbers = []
    timer_thread = None
    is_running = False
    bingo = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = threading.Lock()

    def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'game_{self.game_id}'
        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

        from game.models import Game
        game = Game.objects.get(id=int(self.game_id))
        self.game_random_numbers = json.loads(game.random_numbers)

    def disconnect(self, close_code):
        # Leave room group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        data = json.loads(text_data)

        if data['type'] == 'game_start':
            from game.models import Game
            game = Game.objects.get(id=int(self.game_id))

            if game.played == "Started" and game.numberofplayers > 1:
                    
                self.send(text_data=json.dumps({
                    'type': 'timer_message',
                    'message': str(game.started_at)
                }))

                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'game_start',
                        'message': 'Start Game' 
                    }
                )

                if not self.is_running:
                    self.is_running = True
                    self.timer_thread = threading.Thread(target=self.send_random_numbers_periodically)
                    self.timer_thread.start()

        if data['type'] == 'bingo':
            async_to_sync(self.checkBingo(int(data['userId']), data['calledNumbers']))
            if self.bingo:
                self.is_running = False
                if self.timer_thread:
                    self.timer_thread.join()
                if self.game_id in active_games:
                    del active_games[self.game_id]
            else:
                self.block(int(data['user_id']))

        if data['type'] == 'select_number':
            self.add_player(data['player_id'], data['card_id'])

        if data['type'] == 'remove_number':
            self.remove_player(data['player_id'], data['card_id'])

    def send_random_numbers_periodically(self):
        from game.models import Game
        game = Game.objects.get(id=self.game_id)
        game.started_at = timezone.now()
        game.save()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'timer_message',
                'message': str(game.started_at)
            }
        )

        # Wait 65 seconds before switching state
        time.sleep(65)
        game.played = 'Playing'
        game.save()

        # Send each number only once
        for num in self.game_random_numbers:
            if not self.is_running:
                break

            with self.lock:
                # Send the random number to all players in the group only once
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'random_number',
                        'random_number': num
                    }
                )
                self.called_numbers.append(num)

            # Wait for a few seconds before sending the next number
            time.sleep(5)

    def random_number(self, event):
        """Handles individual random number events received from group_send."""
        random_number = event['random_number']
        self.send(text_data=json.dumps({
            'type': 'random_number',
            'random_number': random_number
        }))

    def game_start(self, event):
        message = event['message']
        self.send(text_data=json.dumps({
            'type': 'game_start',
            'message': message
        }))

    def timer_message(self, event):
        message = event['message']
        self.send(text_data=json.dumps({
            'type': 'timer_message',
            'message': message
        }))

    def result(self, event):
        result = event['data']
        self.send(text_data=json.dumps({
            'type': 'result',
            'data': result
        }))

    def selected_numbers(self, event):
        selected_numbers = event['selected_numbers']
        self.send(text_data=json.dumps({
            'type': 'selected_numbers',
            'selected_numbers': selected_numbers
        }))

    def checkBingo(self, user_id, calledNumbers):
        from game.models import Card, Game
        from custom_auth.models import AbstractUser, User
        
        game = Game.objects.get(id=int(self.game_id))
        result = []
        
        # Retrieve player's cards based on the provided user_id
        players = json.loads(game.playerCard)
        player_cards = [entry['card'] for entry in players if entry['user'] == user_id]

        if not player_cards:
            # User does not have any cards associated
            result.append({'user_id': user_id, 'message': 'Not a Player'})
            self.send(text_data=json.dumps({
                'type': 'result',
                'data': result
            }))
            return
        
        # Include a zero at the end of the called numbers (for "free space" if applicable)
        called_numbers_list = calledNumbers + [0]
        game.total_calls = len(called_numbers_list)
        game.save_called_numbers(called_numbers_list) 
        game.save()

        from itertools import chain

        # Flatten player_cards if it contains nested lists
        flat_player_cards = list(chain.from_iterable(player_cards)) if isinstance(player_cards[0], list) else player_cards

        # Now, filter using the flat list of IDs
        cards = Card.objects.filter(id__in=flat_player_cards)

        # Loop through all the cards assigned to the user
        for card in cards:
            numbers = json.loads(card.numbers)
            
            # Check if this card has a Bingo with the called numbers
            winning_numbers = self.has_bingo(numbers, called_numbers_list)
            
            if winning_numbers:
                # Bingo achieved
                result.append({
                    'card_name': card.id,
                    'message': 'Bingo',
                    'card': numbers,
                    'winning_numbers': winning_numbers,
                    'called_numbers': called_numbers_list
                })
                
                # Update user’s wallet with the prize
                user = AbstractUser.objects.get(id=user_id)
                acc = User.objects.get(user=user)
                acc.wallet += game.winner_price
                acc.save()
                
                # Close the game
                game.played = "Close"
                game.save()
                
                # Notify all players in the room group about the result
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'result',
                        'data': result
                    }
                )
                return  # Exit once Bingo is found for any card

        # If no Bingo was found for any card
        result.append({
            'user_id': user_id,
            'message': 'No Bingo',
            'cards_checked': player_cards,
            'called_numbers': called_numbers_list
        })
        self.send(text_data=json.dumps({
            'type': 'result',
            'data': result
        }))


    def has_bingo(self, card, called_numbers):
        winning_rows = 0
        winning_diagonals = 0
        winning_columns = 0
        called_numbers_list = list(called_numbers)
        corner_count = 0
        winning_numbers = []

        # Check diagonals
        diagonal2 = [card[i][i] for i in range(len(card))]
        diagonal1 = [card[i][len(card) - 1 - i] for i in range(len(card))]
        if all(number in called_numbers for number in diagonal2):
            winning_diagonals = 2
            winning_numbers.extend([1, 7, 13, 19, 25])
        if all(number in called_numbers for number in diagonal1):
            winning_diagonals = 1
            winning_numbers.extend([5, 9, 13, 17, 21])

        # Check rows
        for row_index, row in enumerate(card):
            if all(number in called_numbers for number in row):
                winning_rows = row_index + 1
                winning_numbers.extend([(row_index * 5) + i + 1 for i in range(5)])

        # Check columns
        for col in range(len(card[0])):
            if all(card[row][col] in called_numbers for row in range(len(card))):
                winning_columns = col + 1
                winning_numbers.extend([winning_columns + (i * 5) for i in range(5)])

        # Check corners
        if card[0][0] in called_numbers:
            corner_count += 1
        if card[0][4] in called_numbers:
            corner_count += 1
        if card[4][0] in called_numbers:
            corner_count += 1
        if card[4][4] in called_numbers:
            corner_count += 1

        if corner_count == 4:
            winning_numbers.extend([1, 5, 21, 25])

        return winning_numbers

    def block(self, card_id):
        from game.models import Game
        last_game = Game.objects.get(id=self.game_id)
        players = json.loads(last_game.playerCard)
        updated_list = [item for item in players if int(item['card']) != card_id]
        last_game.playerCard = json.dumps(updated_list)
        last_game.numberofplayers = len(updated_list)
        last_game.save()

    def add_player(self, player_id, card_id):
        from game.models import Game

        game = Game.objects.get(id=int(self.game_id))

        # Check if game status is not "playing"
        if game.played == "playing":
            # Send a message to the user indicating they can't join
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Cannot join: The game is not currently playing.'
                }
            )
            return  # Exit early since the game is not in the correct state

        # Load the existing player card data or initialize as an empty list
        try:
            players = json.loads(game.playerCard) if game.playerCard else []
        except json.JSONDecodeError:
            players = []

        if isinstance(players, list):
            # Check if player already exists
            player_entry = next((p for p in players if p['user'] == player_id), None)
            if player_entry:
                # If player already exists, add the card to their list if it's not already included
                if isinstance(player_entry['card'], list):
                    if card_id not in player_entry['card']:
                        player_entry['card'].append(card_id)
                else:
                    if player_entry['card'] != card_id:
                        player_entry['card'] = [player_entry['card'], card_id]
            else:
                # If player does not exist, add new entry with the card as a list
                players.append({'user': player_id, 'card': [card_id]})
        else:
            # Initialize players list if it's empty or not properly formatted
            players = [{'user': player_id, 'card': [card_id]}]

        # Save the updated player list and calculate the accurate total number of cards
        game.playerCard = json.dumps(players)
        game.numberofplayers = sum(len(p['card']) if isinstance(p['card'], list) else 1 for p in players)  # Count all cards accurately
        game.save()

        async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'sucess',
                    'message': 'Game will start soon'
                }
        )

        # Broadcast the updated player list over the socket
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'update_player_list',
                'player_list': players
            }
        )

    def remove_player(self, player_id, card_id):
        from game.models import Game
        game = Game.objects.get(id=int(self.game_id))

        # Update the player list in the database
        players = json.loads(game.playerCard)
        updated_list = [player for player in players if player['user'] != player_id or player['card'] != card_id]
        game.playerCard = json.dumps(updated_list)
        game.numberofplayers = len(updated_list)
        game.save()

        # Broadcast the updated player list over the socket
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'update_player_list',
                'player_list': updated_list
            }
        )

    def update_player_list(self, event):
        player_list = event['player_list']
        # Send the updated player list to WebSocket clients
        self.send(text_data=json.dumps({
            'type': 'player_list',
            'player_list': player_list
        }))

    def error(self, event):
        message = event['message']
        # Send the updated player list to WebSocket clients
        self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))
    
    def sucess(self, event):
        message = event['message']
        # Send the updated player list to WebSocket clients
        self.send(text_data=json.dumps({
            'type': 'sucess',
            'message': message
        }))