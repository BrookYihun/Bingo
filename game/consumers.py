import json
import threading
import time
from django.utils import timezone
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
import redis
import uuid

class GameConsumer(WebsocketConsumer):
    redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)
    game_threads_started = set()
    lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def connect(self):
        self.stake = self.scope['url_route']['kwargs']['stake']
        self.room_group_name = f'game_{self.stake}'
        self.accept()

        print(f"Connecting to game room: {self.room_group_name}")
        print(f"Stake: {self.stake}")

        # Join group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )

        # Start game scheduler only once per stake
        with self.lock:
            if self.stake not in self.game_threads_started:
                threading.Thread(target=self.auto_game_start_loop, daemon=True).start()
                self.game_threads_started.add(self.stake)

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        data = json.loads(text_data)

        if data['type'] == 'select_number':
            self.add_player(data['player_id'], data['card_id'])

        if data['type'] == 'remove_number':
            self.remove_player(data['userId'])

        if data['type']  == 'joined_bingo':
            user_id = data.get("userId")
            bingo_page_users = self.get_bingo_page_users()
            bingo_page_users.add(user_id)
            self.set_bingo_page_users(bingo_page_users)
            print(f"User {user_id} joined bingo page for game")
        
        if data['type'] == 'bingo':
            async_to_sync(self.checkBingo(int(data['userId']), data['calledNumbers'], data['gameId']))
            bingo = self.get_game_state("bingo", game_id=data['gameId'])
            if bingo:
                self.set_game_state("is_running",False, game_id=data['gameId'])
                if self.game_id in self.active_games:
                    del self.active_games[data['game_id']]
        
        if data['type'] == 'card_data':
            from game.models import Card, Game
            game_id = int(self.game_id)
            game = Game.objects.get(id=game_id)
            
            user_cards = []
            selected_players = self.get_selected_players()
            for player in selected_players:
                if player['user'] == int(data.get("userId")):
                    cards_field = player['card']
                    if isinstance(cards_field, list):
                        def flatten(lst):
                            for item in lst:
                                if isinstance(item, list):
                                    yield from flatten(item)
                                else:
                                    yield int(item)
                        user_cards = list(flatten(cards_field))
                    else:
                        user_cards = [int(cards_field)]
                    break

            if not user_cards:
                print("No cards found for user, skipping response.")
                return  # ✅ Don't send empty card data

            cards = Card.objects.filter(id__in=user_cards)
            bingo_table_data = [
                {
                    "id": card.id,
                    "numbers": json.loads(card.numbers)
                }
                for card in cards
            ]
            print("Sending cards:", bingo_table_data)
            self.send(text_data=json.dumps({
                "type": "card_data",
                "cards": bingo_table_data
            }))
            return

    # --- Redis state helpers ---
    def get_selected_players(self):
        key = f"selected_players_{self.stake}"
        data = self.redis_client.get(key)
        return json.loads(data) if data else []

    def set_selected_players(self, players):
        key = f"selected_players_{self.stake}"
        self.redis_client.set(key, json.dumps(players))

    def get_player_count(self):
        return int(self.redis_client.get(f"player_count_{self.stake}") or 0)

    def set_player_count(self, count):
        self.redis_client.set(f"player_count_{self.stake}", count)

    def get_active_games(self):
        key = f"active_games_{self.stake}"
        data = self.redis_client.get(key)
        return json.loads(data) if data else []

    def set_active_games(self, game_ids):
        key = f"active_games_{self.stake}"
        self.redis_client.set(key, json.dumps(game_ids))

    def increment_game_counter(self):
        return self.redis_client.incr(f"game_counter_{self.stake}")
    
    def get_game_state(self, key, game_id=None):
        game_id = game_id or self.game_id
        val = self.redis_client.get(f"game_state_{game_id}_{key}")
        return json.loads(val) if val else None

    def set_game_state(self, key, value, game_id=None):
        game_id = game_id or self.game_id
        self.redis_client.set(f"game_state_{game_id}_{key}", json.dumps(value))
    
    def get_bingo_page_users(self):
        data = self.redis_client.get(f"bingo_page_users_{self.game_id}")
        return set(json.loads(data)) if data else set()

    def set_bingo_page_users(self, users):
        self.redis_client.set(f"bingo_page_users_{self.game_id}", json.dumps(list(users)))


    # --- Player management ---
    def add_player(self, player_id, card_id):
        from custom_auth.models import User
        from decimal import Decimal

        selected_players = self.get_selected_players()
        selected_players = [p for p in selected_players if p['user'] != player_id]
        card_ids = card_id if isinstance(card_id, list) else [card_id]
        selected_players.append({'user': player_id, 'card': card_ids})
        self.set_selected_players(selected_players)

        player_count = sum(len(p['card']) for p in selected_players)
        self.set_player_count(player_count)

        user = User.objects.get(id=player_id)
        if user.wallet < Decimal(self.stake) * len(card_ids):
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Insufficient balance to join the game.'
                }
            )
            return

        self.broadcast_player_list()

    def remove_player(self, player_id):
        selected_players = [p for p in self.get_selected_players() if p['user'] != player_id]
        self.set_selected_players(selected_players)
        self.set_player_count(sum(len(p['card']) for p in selected_players))
        self.broadcast_player_list()

    def broadcast_player_list(self):
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'update_player_list',
                'player_list': self.get_selected_players()
            }
        )
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'game_stat',
                'number_of_players': self.get_player_count(),
                'stake': self.stake
            }
        )

    # --- Automatic Game Loop ---
    def auto_game_start_loop(self):
        while True:
            time.sleep(30)
            selected_players = self.get_selected_players()
            player_count = self.get_player_count()
            active_games = self.get_active_games()

            if player_count >= 3 and len(active_games) < 2:
                from game.models import Game  # ✅ Make sure it's the correct path
                from django.utils import timezone
                import random
                
                # Build the playerCard map: {user_id: [card_ids]}
                player_card_map = {
                    str(p['user']): p['card'] for p in selected_players
                }
                
                # Random numbers to call
                random_numbers = random.sample(range(1, 91), 90)  # Example: 1 to 90
                
                # Calculate number of cards
                number_of_cards = sum(len(c) for c in player_card_map.values())
                
                # Create game in DB
                new_game = Game.objects.create(
                    stake=self.stake,
                    numberofplayers=number_of_cards,
                    playerCard=player_card_map,
                    random_numbers={'numbers': random_numbers},
                    called_numbers={'numbers': []},
                    winner_price=0,  # Can be updated later
                    admin_cut=0,     # Can be calculated
                    created_at=timezone.now(),
                    started_at=timezone.now(),
                    played='Started'
                )
                
                # Add game_id to Redis active games
                active_games.append(new_game.id)
                self.set_active_games(active_games)
                
                # Broadcast the game start
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'game_started',
                        'game_id': new_game.id,
                        'player_list': selected_players,
                        'stake': self.stake
                    }
                )

                threading.Thread(
                    target=self.start_game_with_random_numbers,
                    args=(new_game, selected_players),
                    daemon=True
                ).start()

                # Reset players for new cycle
                self.set_selected_players([])
                self.set_player_count(0)
    
    def start_game_with_random_numbers(self, game, selected_players):
        from custom_auth.models import User
        from decimal import Decimal
        import random
        import json

        # Add helper attribute
        self.game_id = game.id
        self.room_group_name = f"game_room_{game.id}"
        self.set_game_state("is_running", True)

        # Timer before start
        start_delay = 30
        start_time_with_delay = game.started_at + timezone.timedelta(seconds=start_delay)
        remaining = (start_time_with_delay - timezone.now()).total_seconds()
        remaining_seconds = max(int(remaining), 0)

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'timer_message',
                'remaining_seconds': remaining_seconds,
                'message': str(game.started_at),
            }
        )

        time.sleep(start_delay)  # Wait for 30 seconds
        game.played = 'Playing'
        game.save()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'playing',
                'message': 'Game is now playing'
            }
        )

        # Deduct balance only from players in bingo page
        stake_amount = Decimal(game.stake)
        updated_player_cards = []
        total_cards = sum(len(player["card"]) for player in selected_players)
        bingo_users = self.get_bingo_page_users()  # Your existing method

        for entry in selected_players:
            try:
                user_id = entry["user"]
                cards = entry["card"]
                flat_cards = [c for sub in cards for c in sub] if isinstance(cards[0], list) else cards
                total_deduction = stake_amount * len(flat_cards)
                user = User.objects.get(id=user_id)

                if user_id in bingo_users:
                    if user.wallet >= total_deduction:
                        user.wallet -= total_deduction
                        user.save()
                        entry["card"] = flat_cards
                        updated_player_cards.append(entry)
                    else:
                        self.remove_player(user_id)
                else:
                    self.remove_player(user_id)
            except Exception as e:
                print(f"[Deduction Error] {e}")

        # Update DB
        game.numberofplayers = len(updated_player_cards)
        game.playerCard = updated_player_cards

        winner_price = stake_amount * sum(len(p['card']) for p in updated_player_cards)
        if winner_price >= 100:
            admin_cut = winner_price * Decimal('0.2')
            winner_price -= admin_cut
            game.admin_cut = admin_cut
        game.winner_price = winner_price
        game.save()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'game_stats',
                'number_of_players': game.numberofplayers,
                'stake': game.stake,
                'winner_price': float(game.winner_price),
                'bonus': game.bonus
            }
        )

        # Now send random numbers every 5 seconds
        called = []
        for num in game.random_numbers.get("numbers", []):
            if not self.get_game_state("is_running"):
                break

            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'random_number',
                    'random_number': num
                }
            )

            called.append(num)
            self.set_game_state("called_numbers", called)

            time.sleep(5)

        # Finish
        time.sleep(10)
        game.played = 'closed'
        game.save()
        self.set_game_state("is_running", False)

        active_games = self.get_active_games()
        if self.game_id in active_games:
            active_games.remove(self.game_id)
            self.set_active_games(active_games)

        self.close()

    def checkBingo(self, user_id, calledNumbers, game_id):
        from game.models import Card, Game
        from custom_auth.models import User
        
        game = Game.objects.get(id=int(game_id))
        result = []
        
        # Retrieve player's cards based on the provided user_id
        print(game.playerCard)
        selected_players = self.get_selected_players()
        players = selected_players
        player_cards = [entry['card'] for entry in players if entry['user'] == user_id]

        if not player_cards:
            # User does not have any cards associated
            result.append({'user_id': user_id, 'message': 'Not a Player'})
            self.send(text_data=json.dumps({
                'type': 'result',
                'data': result
            }))
            return
        
        # Flatten it safely
        def flatten(lst):
            for item in lst:
                if isinstance(item, list):
                    yield from flatten(item)
                else:
                    yield item

        user_cards = list(flatten(player_cards))

        print(f"Checking Bingo for user {user_id} with cards: {user_cards}")
        
        if game.winner != 0:
            return
        
        if game.played == 'closed':
            return 
        
        # Include a zero at the end of the called numbers (for "free space" if applicable)
        if not set(calledNumbers).issubset(self.get_game_state("called_numbers") or []):
            print("Called numbers do not match the game's called numbers.")
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

        # Fetch the Card objects
        cards = Card.objects.filter(id__in=user_cards)

        print(f"Cards for user {user_id}: {[card.id for card in cards]}")

        # Loop through all the cards assigned to the user
        for card in cards:
            numbers = json.loads(card.numbers)
            print(f"Checking card {card.id} for user {user_id} with numbers: {numbers}")
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

    # --- WebSocket Handlers ---
    def update_player_list(self, event):
        self.send(text_data=json.dumps({
            'type': 'player_list',
            'player_list': event['player_list']
        }))

    def game_stat(self, event):
        self.send(text_data=json.dumps({
            'type': 'game_stat',
            'number_of_players': event['number_of_players'],
            'stake': event['stake']
        }))

    def game_started(self, event):
        self.send(text_data=json.dumps({
            'type': 'game_started',
            'game_id': event['game_id'],
            'player_list': event['player_list'],
            'stake': event['stake']
        }))

    def error(self, event):
        self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message']
        }))
