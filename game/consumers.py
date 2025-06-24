import json
import threading
import time
from django.utils import timezone
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
import redis

active_games = {}

class GameConsumer(WebsocketConsumer):
    game_random_numbers = []
    called_numbers = []
    lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

    def get_game_state(self, key):
        """
        Retrieve game state from Redis.
        """
        redis_key = f"game_state_{self.game_id}"
        state = self.redis_client.hget(redis_key, key)
        if state:
            return json.loads(state)
        return None

    def set_game_state(self, key, value):
        """
        Save game state to Redis.
        """
        redis_key = f"game_state_{self.game_id}"
        self.redis_client.hset(redis_key, key, json.dumps(value))

    def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'game_{self.game_id}'
        from game.models import Game
        try:
            game = Game.objects.get(id=int(self.game_id))
            
            # Check if the game is already closed
            if game.played == 'closed':
                self.close()
                return

            self.accept()
            
            if game.played == 'Playing':
                self.send(text_data=json.dumps({
                    'type': 'called_numbers',
                    'called_numbers': self.called_numbers
                }))
            
            if game.played == 'Started':
                self.send(text_data=json.dumps({
                    'type': 'timer_message',
                    'message': str(game.started_at)
                }))
            
            self.game_random_numbers = json.loads(game.random_numbers)
            
            bingo = self.get_game_state("bingo")
            is_running = self.get_game_state("is_running")
            if not bingo:
                self.set_game_state("bingo", False)
            if not is_running:
                self.set_game_state("is_running", False)
            
            # Join room group
            async_to_sync(self.channel_layer.group_add)(
                self.room_group_name,
                self.channel_name
            )
        except Game.DoesNotExist:
            # If the game does not exist, close the connection
            self.close()

    def disconnect(self, close_code):
        # Leave room group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        data = json.loads(text_data)
        is_running = self.get_game_state("is_running")
        bingo = self.get_game_state("bingo")

        if data['type'] == 'game_start':
            from game.models import Game
            game = Game.objects.get(id=int(self.game_id))

            if game.played == "Created":
                game.started_at = timezone.now()
                game.played = 'Started'
                game.save()
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

                if not is_running:
                    self.set_game_state("is_running",True)

                    thread = threading.Thread(target=self.send_random_numbers_periodically)
                    thread.start()


        if data['type'] == 'bingo':
            async_to_sync(self.checkBingo(int(data['userId']), data['calledNumbers']))
            bingo = self.get_game_state("bingo")
            if bingo:
                self.set_game_state("is_running",False)
                if self.game_id in active_games:
                    del active_games[self.game_id]
                # self.close()  # Disconnect the WebSocket after a bingo
            # else:
            #     self.send(text_data=json.dumps({
            #         'type': 'no_bingo',
            #         'message': 'No Bingo! Please check your numbers and try again.'
            #     }))
                # self.block(int(data['userId']))

        if data['type'] == 'select_number':
            self.add_player(data['player_id'], data['card_id'])

        if data['type'] == 'remove_number':
            self.remove_player(data['player_id'])

    def send_random_numbers_periodically(self):
        from game.models import Game
        import json

        is_running = self.get_game_state("is_running")
        game = Game.objects.get(id=self.game_id)
        players = json.loads(game.playerCard)
        total_cards = sum(len(sublist) for player in players for sublist in player["card"])
        game.numberofplayers = int(total_cards)
        print(total_cards)
        winner_price = total_cards * int(game.stake)
        if winner_price >= 100:
            admin_cut = winner_price * 0.2
            winner_price = winner_price - admin_cut
            game.admin_cut = admin_cut
        game.winner_price = winner_price 
        game.save()        

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'timer_message',
                'message': str(game.started_at)
            }
        )

        # Wait 65 seconds before switching state
        time.sleep(30)
        game.played = 'Playing'
        game.save()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'playing',
                'message': 'game is now playing' 
            }
        )

        from decimal import Decimal
        from custom_auth.models import User

        stake_amount = Decimal(game.stake)

        # Convert string to Python object
        player_cards_raw = game.playerCard
        if isinstance(player_cards_raw, str):
            player_cards = json.loads(player_cards_raw)
        else:
            player_cards = player_cards_raw

        # Now iterate over the list of players
        for entry in player_cards:
            try:
                user_id = entry["user"]
                cards = entry["card"]  # cards = [[57, 69]]
                # Flatten the nested list to count total card IDs
                flattened_cards = [card_id for sublist in cards for card_id in sublist]
                num_cards = len(flattened_cards) 
                total_deduction = stake_amount * num_cards

                user = User.objects.get(id=user_id)

                if user.wallet >= total_deduction:
                    user.wallet -= total_deduction
                    user.save()
                else:
                    self.remove_player(self,user_id)
                    # Optionally remove them from game or notify them here

            except User.DoesNotExist:
                print(f"User with id {user_id} not found.")
            except Exception as e:
                print(f"Error processing deduction: {e}")


        # Send each number only once
        for num in self.game_random_numbers:
            is_running = self.get_game_state("is_running")
            if not is_running:
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

        # Close the game after all numbers are sent
        time.sleep(10)
        game.played = 'closed'
        game.save()
        self.set_game_state("is_running",False)

        # Remove from active games and disconnect the consumer
        if self.game_id in active_games:
            del active_games[self.game_id]
        self.close()  # Disconnect the WebSocket after sending all numbers


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

    def playing(self, event):
        message = event['message']
        self.send(text_data=json.dumps({
            'type': 'playing',
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
        from custom_auth.models import User
        
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
        
        if game.winner != 0:
            return
        
        if game.played == 'closed':
            return 
        
        # Include a zero at the end of the called numbers (for "free space" if applicable)
        if not set(calledNumbers).issubset(self.called_numbers):
            return
        
        called_numbers_list = calledNumbers + [0]
        game.total_calls = len(called_numbers_list)
        game.save_called_numbers(called_numbers_list) 
        game.save()
        
        def flatten_card_ids(card_list):
            """Recursively flatten card IDs to handle any nested lists."""
            flattened = []
            for card in card_list:
                if isinstance(card, list):
                    flattened.extend(flatten_card_ids(card))
                else:
                    flattened.append(int(card))
            return flattened
        
        # Find and flatten all card IDs for the specified user
        user_cards = []
        for player in players:
            if player['user'] == int(user_id):
                # Flatten card IDs for this player
                user_cards.extend(flatten_card_ids(player['card'] if isinstance(player['card'], list) else [player['card']]))

        # Fetch the Card objects
        cards = Card.objects.filter(id__in=user_cards)

        # Loop through all the cards assigned to the user
        for card in cards:
            numbers = json.loads(card.numbers)
            
            # Check if this card has a Bingo with the called numbers
            winning_numbers = self.has_bingo(numbers, called_numbers_list)
            
            if winning_numbers:
                
                acc = User.objects.get(id=user_id)
                
                # Bingo achieved
                result.append({
                    'card_name': card.id,
                    'message': 'Bingo',
                    'name': acc.name,
                    'user_id': acc.id,
                    'card': json.loads(card.numbers),
                    'winning_numbers': winning_numbers,
                    'called_numbers': called_numbers_list
                })
                
                # Close the game
                game.played = "closed"
                game.winner = user_id
                game.save()
                
                # Notify all players in the room group about the result
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'result',
                        'data': result
                    }
                )
                bingo = self.get_game_state("bingo")
                if bingo == False:
                    acc.wallet += game.winner_price
                    acc.save()
                    self.set_game_state("bingo",True)
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
        winning_columns = 0
        corner_count = 0
        winning_numbers = []

        print("Checking card for Bingo:", card)
        print("Called numbers:", called_numbers)

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

    def block(self, user_id):
        from game.models import Game
        last_game = Game.objects.get(id=self.game_id)
        players = json.loads(last_game.playerCard)
        updated_list = [item for item in players if int(item['user']) != user_id]
        last_game.playerCard = json.dumps(updated_list)
        last_game.numberofplayers = len(updated_list)
        last_game.save()

    def add_player(self, player_id, card_id):
        from game.models import Game
        from custom_auth.models import User
        from decimal import Decimal

        game = Game.objects.get(id=int(self.game_id))

        # ✅ Check for multiple active games with the same stake (not Closed)
        active_games_with_same_stake = Game.objects.filter(
            stake=game.stake,
            played__in=['Created', 'Started', 'playing']
        ).exclude(id=game.id).count()

        if active_games_with_same_stake >= 2:
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Please wait: Maximum number of active games for this stake is reached.'
                }
            )
            return  # ❌ Do not proceed further

        # ❗Only allow joining if the game is not "playing"
        if game.played == "playing":
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Cannot join: The game is already in progress.'
                }
            )
            return

        # ✅ Load or initialize playerCard
        try:
            players = json.loads(game.playerCard) if game.playerCard else []
        except json.JSONDecodeError:
            players = []

        if isinstance(players, list):
            player_entry = next((p for p in players if p['user'] == player_id), None)
            if player_entry:
                if isinstance(player_entry['card'], list):
                    if card_id not in player_entry['card']:
                        player_entry['card'].append(card_id)
                else:
                    if player_entry['card'] != card_id:
                        player_entry['card'] = [player_entry['card'], card_id]
            else:
                players.append({'user': player_id, 'card': [card_id]})
        else:
            players = [{'user': player_id, 'card': [card_id]}]

        # ✅ Balance Check
        user = User.objects.get(id=player_id)
        card_list = card_id if isinstance(card_id, list) else [card_id]
        total_cost = Decimal(game.stake) * len(card_list)

        if user.wallet < total_cost:
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Insufficient balance to join the game.'
                }
            )
            return

        # Optional wallet deduction (currently commented out)
        # user.wallet -= total_cost
        # user.save()

        # ✅ Save game updates
        game.playerCard = json.dumps(players)
        game.numberofplayers = sum(len(p['card']) if isinstance(p['card'], list) else 1 for p in players)
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

    def remove_player(self, player_id):
        from game.models import Game
        game = Game.objects.get(id=int(self.game_id))

        # Update the player list in the database
        players = json.loads(game.playerCard)
        updated_list = [player for player in players if player['user'] != player_id]
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