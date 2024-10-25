from django.utils import timezone
import threading
import time
from channels.generic.websocket import WebsocketConsumer
import json
from asgiref.sync import sync_to_async, async_to_sync

active_games = {}

class GameConsumer(WebsocketConsumer):
    game_random_numbers = []
    called_numbers = []
    timer_thread = None
    is_running = False
    bingo = False
    def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = 'game_%s' % self.game_id
        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()
        from game.models import Game
        game = Game.objects.get(id=int(self.game_id))
        self.game_random_numbers = json.loads(game.random_numbers)
        if game.played == "Started":
            elapsed_time = (timezone.now() - game.started_at).total_seconds()
            if elapsed_time > 60:
                game.played == 'Playing'
                game.save()
            self.send(text_data=json.dumps({
                'type': 'timer_message',
                'message': str(game.started_at)
            }))
            self.send(text_data=json.dumps({
                'type': 'game_start',
                'message': 'Start Game'
            }))

    def disconnect(self, close_code):
        # Leave room group
        self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
                
    # Receive message from WebSocket
    def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'game_start':
            async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'game_start',
                        'message': 'Start Game' 
                    }
                )
            self.is_running = True
            self.timer_thread = threading.Thread(target=self.send_random_numbers_periodically)
            self.timer_thread.start()
        
        if data['type'] == 'bingo':
            async_to_sync(self.checkBingo(int(data['card_id']),data['calledNumbers']))
            if self.bingo == True:
                self.is_running = False
                if self.timer_thread:
                    self.timer_thread.join()
                # Remove game from active games if it exists
                if self.game_id in active_games:
                    del active_games[self.game_id]
            else:
                self.block(int(data['card_id']))
            
            # Broadcast message to all connected players
        
        if data['type'] == 'selected_numbers':
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'selected_numbers',
                    'selected_numbers': data['selected_numbers']
                }
            )
    
    def send_random_numbers_periodically(self):
        from game.models import Game
        game = Game.objects.get(id=self.game_id)
        game.played = "Started"
        game.started_at = timezone.now()
        game.save()
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'timer_message',
                'message': str(game.started_at)
            }
        )
        time.sleep(65)
        game.played = 'Playing'
        game.save()
        for num in self.game_random_numbers:
            if self.is_running:
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'random_number',
                        'random_number': num
                    }
                )
                async_to_sync(self.called_numbers.append(num))
                time.sleep(5)
                               
    
    def message(self,text_data):
        self.send({
            'type':'ramdom_number',
            'random_number': text_data.get("random_number")
        })
    
    def random_number(self, event):
    # This method will handle messages of type 'random_number'
        random_number = event['random_number']
        # Handle the received random number as needed
        # For example, you can send it to the client or perform other actions
        self.send(text_data=json.dumps({
            'type': 'random_number',
            'random_number': random_number
        }))
    
    def game_start(self, event):
    # This method will handle messages of type 'random_number'
        message = event['message']
        # Handle the received random number as needed
        # For example, you can send it to the client or perform other actions
        self.send(text_data=json.dumps({
            'type': 'game_start',
            'message': message
        }))
    
    def timer_message(self, event):
    # This method will handle messages of type 'random_number'
        message = event['message']
        # Handle the received random number as needed
        # For example, you can send it to the client or perform other actions
        self.send(text_data=json.dumps({
            'type': 'timer_message',
            'message': message
        }))

    def result(self, event):
    # This method will handle messages of type 'random_number'
        result = event['data']
        # Handle the received random number as needed
        # For example, you can send it to the client or perform other actions
        self.send(text_data=json.dumps({
            'type': 'result',
            'data': result
        }))
    
    def selected_numbers(self, event):
        selected_numbers = event['selected_numbers']
        # Send the selected numbers to WebSocket clients
        self.send(text_data=json.dumps({
            'type': 'selected_numbers',
            'selected_numbers': selected_numbers
        }))

    
    def checkBingo(self,card_id,calledNumbers):
        from game.models import Card, Game
        game = Game.objects.get(id=int(self.game_id))
        result = []
        players = json.loads(game.playerCard)
        player_cards = [entry['card'] for entry in players]
        card_found = int(card_id) in player_cards
        player_id = next((entry['user'] for entry in players if entry['card'] == card_id), None)
        called_numbers_list = calledNumbers
        called_numbers_list.append(0)
        game.total_calls = len(called_numbers_list)
        game.save_called_numbers(called_numbers_list) 
        game.save()

        if card_found:
            card = Card.objects.get(id=card_id)
            numbers = json.loads(card.numbers)
            winning_numbers = self.has_bingo(numbers, called_numbers_list)
            if len(winning_numbers)>0:
                from custom_auth.models import AbstractUser
                result.append({'card_name': card.id, 'message': 'Bingo', 'card': numbers, 'winning_numbers':winning_numbers,'called_numbers':called_numbers_list})
                user = AbstractUser.objects.get(id=player_id)
                from custom_auth.models import User
                acc = User.objects.get(user=user)
                acc.wallet = acc.wallet + game.winner_price
                acc.save()
                game.played = "Close"
                game.save()
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'result',
                        'data': result
                    }
                )
            else:
                result.append({'card_name': card.id, 'message': 'No Bingo','card':numbers})
                self.send(text_data=json.dumps({
                    'type': 'result',
                    'data': result
                }))
        else:
            result.append({'card_name': card_id, 'message': 'Not a Player'})
        

    def has_bingo(self,card, called_numbers):
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
            winning_numbers.append(1)
            winning_numbers.append(7)
            winning_numbers.append(13)
            winning_numbers.append(19)
            winning_numbers.append(25)
            break_index = max([called_numbers_list.index(number) for number in diagonal2 if number in called_numbers_list]) + 1
        if all(number in called_numbers for number in diagonal1):
            winning_diagonals = 1
            winning_numbers.append(5)
            winning_numbers.append(9)
            winning_numbers.append(13)
            winning_numbers.append(17)
            winning_numbers.append(21)
            break_index = max([called_numbers_list.index(number) for number in diagonal1 if number in called_numbers_list]) + 1

        # Check rows
        for row_index, row in enumerate(card):
            if all(number in called_numbers for number in row):
                winning_rows = row_index + 1
                winning_numbers.append((row_index*5)+1)
                winning_numbers.append((row_index*5)+2)
                winning_numbers.append((row_index*5)+3)
                winning_numbers.append((row_index*5)+4)
                winning_numbers.append((row_index*5)+5)
                break_index = max([called_numbers_list.index(number) for number in row if number in called_numbers_list]) + 1

        # Check columns
        for col in range(len(card[0])):
            if all(card[row][col] in called_numbers for row in range(len(card))):
                winning_columns = col + 1
                winning_numbers.append(winning_columns)
                winning_numbers.append(winning_columns+5)
                winning_numbers.append(winning_columns+10)
                winning_numbers.append(winning_columns+15)
                winning_numbers.append(winning_columns+20)
                column = [card[row][col] for row in range(len(card))]
                max_index = max([called_numbers_list.index(number) for number in column if number in called_numbers_list])
                break_index = max_index + 1 if max_index >= 0 else 0

        # Check the top-left corner (1, 1)
        if card[0][0] in called_numbers:
            corner_count += 1

        # Check the top-right corner (1, 5)
        if card[0][4] in called_numbers:
            corner_count += 1

        # Check the bottom-left corner (5, 1)
        if card[4][0] in called_numbers:
            corner_count += 1

        # Check the bottom-right corner (5, 5)
        if card[4][4] in called_numbers:
            corner_count += 1

        if corner_count == 4:
            winning_numbers.append(1)
            winning_numbers.append(5)
            winning_numbers.append(21)
            winning_numbers.append(25)

        print(winning_numbers)
        return winning_numbers

    def block(self,card_id):
        from game.models import Game
        last_game = Game.objects.get(id=self.game_id)
        players = json.loads(last_game.playerCard)
        updated_list = [item for item in players if int(item['card']) != card_id]
        last_game.playerCard = json.dumps(updated_list)
        last_game.numberofplayers = len(updated_list)
        last_game.save()

