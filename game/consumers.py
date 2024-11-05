from django.utils import timezone
import threading
import time
from channels.generic.websocket import WebsocketConsumer
import json
from asgiref.sync import async_to_sync

active_games = {}

class GameConsumer(WebsocketConsumer):
    game_random_numbers = []
    called_numbers = []
    timer_thread = None
    is_running = False
    bingo = False

    def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'game_{self.game_id}'

        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

        # Load game data
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
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'game_start':
                self.handle_game_start(data)
            elif message_type == 'bingo':
                self.handle_bingo(data)
            elif message_type == 'select_number':
                self.add_player(data['player_id'], data['card_id'])
            elif message_type == 'remove_number':
                self.remove_player(data['player_id'], data['card_id'])
            else:
                self.handle_unknown_message_type(message_type)
        except Exception as e:
            self.send_error_message(f"Error processing message: {str(e)}")

    def handle_game_start(self, data):
        from game.models import Game
        game = Game.objects.get(id=int(self.game_id))

        if game.played == "Started" and game.numberofplayers > 1:
            elapsed_time = (timezone.now() - game.started_at).total_seconds()
            if elapsed_time > 60:
                game.played = 'Playing'
                game.save()

            self.send(text_data=json.dumps({
                'type': 'timer_message',
                'message': str(game.started_at)
            }))

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {'type': 'game_start', 'message': 'Start Game'}
        )

        self.is_running = True
        self.timer_thread = threading.Thread(target=self.send_random_numbers_periodically)
        self.timer_thread.start()

    def handle_bingo(self, data):
        user_id = int(data['userId'])
        called_numbers = data['calledNumbers']

        async_to_sync(self.check_bingo)(user_id, called_numbers)
        if self.bingo:
            self.is_running = False
            if self.timer_thread:
                self.timer_thread.join()
            if self.game_id in active_games:
                del active_games[self.game_id]
        else:
            self.block(user_id)

    def send_random_numbers_periodically(self):
        from game.models import Game
        game = Game.objects.get(id=self.game_id)
        game.played = "Started"
        game.started_at = timezone.now()
        game.save()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {'type': 'timer_message', 'message': str(game.started_at)}
        )

        time.sleep(65)
        game.played = 'Playing'
        game.save()

        for num in self.game_random_numbers:
            if self.is_running:
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {'type': 'random_number', 'random_number': num}
                )
                self.called_numbers.append(num)
                time.sleep(5)

    def random_number(self, event):
        self.send(json.dumps({'type': 'random_number', 'random_number': event['random_number']}))

    def game_start(self, event):
        self.send(json.dumps({'type': 'game_start', 'message': event['message']}))

    def timer_message(self, event):
        self.send(json.dumps({'type': 'timer_message', 'message': event['message']}))

    def result(self, event):
        self.send(json.dumps({'type': 'result', 'data': event['data']}))

    def selected_numbers(self, event):
        self.send(json.dumps({'type': 'selected_numbers', 'selected_numbers': event['selected_numbers']}))

    def check_bingo(self, user_id, called_numbers):
        from game.models import Card, Game
        from custom_auth.models import AbstractUser, User

        game = Game.objects.get(id=int(self.game_id))
        result = []
        
        # Retrieve player's cards based on the provided user_id
        players = json.loads(game.playerCard)
        player_cards = [entry['card'] for entry in players if entry['user'] == user_id]

        if not player_cards:
            result.append({'user_id': user_id, 'message': 'Not a Player'})
            self.send(json.dumps({'type': 'result', 'data': result}))
            return

        called_numbers_list = called_numbers + [0]
        game.total_calls = len(called_numbers_list)
        game.save_called_numbers(called_numbers_list)
        game.save()

        cards = Card.objects.filter(id__in=player_cards)
        for card in cards:
            numbers = json.loads(card.numbers)
            winning_numbers = self.has_bingo(numbers, called_numbers_list)

            if winning_numbers:
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
        winning_numbers = []

        # Check diagonals
        diagonal2 = [card[i][i] for i in range(len(card))]
        diagonal1 = [card[i][len(card) - 1 - i] for i in range(len(card))]
        if all(number in called_numbers for number in diagonal2):
            winning_numbers.extend([1, 7, 13, 19, 25])
        if all(number in called_numbers for number in diagonal1):
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
        corners = [card[0][0], card[0][4], card[4][0], card[4][4]]
        if all(corner in called_numbers for corner in corners):
            winning_numbers.extend([1, 5, 21, 25])

        return winning_numbers

    def handle_unknown_message_type(self, message_type):
        self.send_error_message(f"No handler for message type {message_type}")

    def send_error_message(self, message):
        self.send(json.dumps({'type': 'error', 'message': message}))
