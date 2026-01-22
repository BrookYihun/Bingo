import json
import threading
import time
import random

from django.template.defaultfilters import lower
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

    def regenerate_card_numbers(self, card, existing_cards):
        new_card = []
        used_numbers = set()
    
        for i in range(5):
            row = []
            for j in range(5):
                # Skip free center spot if you want (j==2 and i==2)
                if i == 2 and j == 2:
                    row.append(0)
                else:
                    lower_bound = j * 15 + 1
                    upper_bound = (j + 1) * 15
                    num = random.randint(lower_bound, upper_bound)
                    while num in used_numbers:
                        num = random.randint(lower_bound, upper_bound)
                    used_numbers.add(num)
                    row.append(num)
            new_card.append(row)
    
        # Convert to a tuple of tuples for hashability (so we can check uniqueness)
        card_key = tuple(tuple(r) for r in new_card)
    
        # Ensure uniqueness across all cards
        while card_key in existing_cards:
            # If duplicate found, regenerate again
            return self.regenerate_card_numbers(card, existing_cards)
    
        # Save new card
        card.numbers = json.dumps(new_card)
        card.save(update_fields=['numbers'])
    
        # Mark as used
        existing_cards.add(card_key)
    
        return new_card
    
    
    def regenerate_all_cards(self):
        from game.models import Card, Game
    
        # Get all active games that are running
        active_games = Game.objects.filter(played='Playing')
        active_cards = set()
    
        for game in active_games:
            # Flatten player cards for this game
            for player in game.playerCard:
                for card_id in player['card']:
                    if isinstance(card_id, list):
                        active_cards.update(card_id)
                    else:
                        active_cards.add(card_id)
    
        # Only regenerate cards NOT in active games
        cards_to_regen = Card.objects.exclude(id__in=active_cards)
        total = cards_to_regen.count()
    
        existing_cards = set()
        for i, card in enumerate(cards_to_regen, 1):
            self.regenerate_card_numbers(card, existing_cards)

    def connect(self):
        self.stake = self.scope['url_route']['kwargs']['stake']
        self.room_group_name = f'game_{self.stake}'
        self.accept()

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )

        if self.room_group_name == "all":

            self.send(text_data=json.dumps({
                "type": "active_game_data",
                "data": self.get_all_active_games()
            }))

        else:
            current_game_id = self.get_stake_state("current_game_id")
            is_running = self.get_game_state("is_running", current_game_id) if current_game_id else False

            if is_running:
                from game.models import Game
                try:
                    current_game = Game.objects.get(id=current_game_id)
                    # Bonus text logic
                    stake_value = int(self.stake or 0)
                    if stake_value in [10, 20, 50] and current_game.numberofplayers >= 10:
                        bonus_text = "10X"
                    else:
                        bonus_text = ""

                    stats = {
                        "type": "game_stat",
                        'number_of_players': current_game.numberofplayers,
                        'stake': current_game.stake,
                        'winner_price': float(current_game.winner_price),
                        'bonus': bonus_text,
                        'game_id': current_game.id,
                        "running": True,
                        "called_numbers": self.get_game_state("called_numbers", current_game_id) or [],
                    }
                    self.send(text_data=json.dumps({
                        "type": "game_in_progress",
                        "game_id": current_game_id
                    }))
                except Game.DoesNotExist:
                    self.try_start_game()
                    stats = {
                        "type": "game_stat",
                        "running": False,
                        "message": "No game is currently running.",
                        "number_of_players": self.get_player_count(),
                        "remaining_seconds": self.get_remaining_time(),
                    }
            else:
                self.try_start_game()
                stats = {
                    "type": "game_stat",
                    "running": False,
                    "message": "No game is currently running.",
                    "number_of_players": self.get_player_count(),
                    "remaining_seconds": self.get_remaining_time(),
                }

            self.send(text_data=json.dumps(stats))
            self.send(text_data=json.dumps({
                'type': 'player_list',
                'player_list': self.get_selected_players()
            }))

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        # Handle empty or None messages
        if not text_data or text_data.strip() == "":
            self.send(text_data=json.dumps({
                "type": "error",
                "message": "Empty message received."
            }))
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            self.send(text_data=json.dumps({
                "type": "error",
                "message": "Invalid JSON format."
            }))
            return

        if data['type'] == 'select_number':

            current_game_id = self.get_stake_state("current_game_id")
            is_running = self.get_game_state("is_running", current_game_id) if current_game_id else False

            if is_running:
                self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "Game already in progress. Please wait for the next round."
                }))
                return

            self.add_player(data['player_id'], data['card_id'])

        if data['type'] == 'remove_number':
            self.remove_player(data['userId'])

        if data['type'] == 'bingo':
            async_to_sync(self.checkBingo(int(data['userId']), data['calledNumbers'], data['gameId']))
            bingo = self.get_game_state("bingo", game_id=data['gameId'])
            if bingo:
                self.set_game_state("is_running", False, game_id=data['gameId'])
                self.set_stake_state("current_game_id", None)
                self.set_selected_players([])
                self.set_player_count(0)
                self.broadcast_player_list()

        if data['type'] == 'card_data':
            from game.models import Card

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
                self.send(text_data=json.dumps({
                    "type": "no_cards",
                    "message": "No cards found for user."
                }))
                return  # ✅ Don't send empty card data

            cards = Card.objects.filter(id__in=user_cards)
            bingo_table_data = [
                {
                    "id": card.id,
                    "numbers": json.loads(card.numbers)
                }
                for card in cards
            ]
            self.send(text_data=json.dumps({
                "type": "card_data",
                "cards": bingo_table_data
            }))
            return

        if data['type'] == "get_stake_stat":
            current_game_id = self.get_stake_state("current_game_id")
            is_running = self.get_game_state("is_running", current_game_id) if current_game_id else False

            if is_running:
                from game.models import Game
                try:
                    current_game = Game.objects.get(id=current_game_id)
                    # Bonus text logic
                    stake_value = int(self.stake or 0)
                    if stake_value in [10, 20, 50] and current_game.numberofplayers >= 10:
                        bonus_text = "10X"
                    else:
                        bonus_text = ""

                    stats = {
                        "type": "game_stat",
                        'number_of_players': current_game.numberofplayers,
                        'stake': current_game.stake,
                        'winner_price': float(current_game.winner_price),
                        'bonus': bonus_text,
                        'game_id': current_game.id,
                        "running": True,
                        "called_numbers": self.get_game_state("called_numbers", current_game_id) or [],
                    }
                except Game.DoesNotExist:
                    stats = {
                        "type": "game_stat",
                        "running": False,
                        "message": "No game is currently running.",
                        "number_of_players": self.get_player_count(),
                        "remaining_seconds": self.get_remaining_time(),
                    }
            else:
                stats = {
                    "type": "game_stat",
                    "running": False,
                    "message": "No game is currently running.",
                    "number_of_players": self.get_player_count(),
                    "remaining_seconds": self.get_remaining_time(),
                }

            self.send(text_data=json.dumps(stats))
            self.send(text_data=json.dumps({
                'type': 'player_list',
                'player_list': self.get_selected_players()
            }))

        if data['type'] == "block_user":
            user_id = data.get("userId")
            if user_id:
                self.block(user_id)
                self.remove_player(user_id)
                self.send(text_data=json.dumps({
                    "type": "user_blocked",
                    "message": f"User {user_id} has been blocked."
                }))
            else:
                self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "User ID not provided."
                }))

        if data['type'] == "fetch_active_game":
            self.send(text_data=json.dumps({
                "type": "active_game_data",
                "data": self.get_all_active_games()
            }))

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

    def get_game_state(self, key, game_id):
        game_id = game_id
        val = self.redis_client.get(f"game_state_{game_id}_{key}")
        return json.loads(val) if val else None

    def set_game_state(self, key, value, game_id):
        game_id = game_id
        self.redis_client.set(f"game_state_{game_id}_{key}", json.dumps(value))

    def get_stake_state(self, key):
        val = self.redis_client.get(f"stake_state_{self.stake}_{key}")
        return json.loads(val) if val else None

    def set_stake_state(self, key, value):
        self.redis_client.set(f"stake_state_{self.stake}_{key}", json.dumps(value))

    def get_bingo_page_users(self):
        data = self.redis_client.get(f"bingo_page_users_{self.stake}")
        return set(json.loads(data)) if data else set()

    def set_bingo_page_users(self, users):
        self.redis_client.set(f"bingo_page_users_{self.stake}", json.dumps(list(users)))

    def end_game(self, game_id):
        self.set_game_state("is_running", False, game_id=game_id)
        self.set_stake_state("current_game_id", None)

    def get_all_active_games(self):
        from .models import Game
        from django.utils import timezone
        import json

        try:
            active_games = {}
            stakes = [10, 20, 30, 40, 50, 100, 150, 200]
            bonus_stakes = {10, 20, 50}  # ✅ Stakes that have bonus

            current_time = timezone.now()
            current_timestamp = current_time.timestamp()

            for stake in stakes:
                stake_str = str(stake)
                stake_key = f"stake_state_{stake}_current_game_id"
                next_start_key = f"stake_state_{stake}_next_game_start"
                player_count_key = f"player_count_{stake}"

                current_game_id = self.redis_client.get(stake_key)
                current_game_id = json.loads(current_game_id) if current_game_id else None

                next_game_start = self.redis_client.get(next_start_key)
                next_game_start = json.loads(next_game_start) if next_game_start else None

                is_running = (
                    self.get_game_state("is_running", current_game_id)
                    if current_game_id
                    else False
                )

                # Default bonus flag
                has_bonus = stake in bonus_stakes

                if is_running and current_game_id:
                    try:
                        current_game = Game.objects.get(id=current_game_id)
                    except Game.DoesNotExist:
                        active_games[stake_str] = {
                            "is_running": False,
                            "remaining_seconds": 0,
                            "winner_price": 0,
                            "bonus": has_bonus,
                        }
                        continue

                    if current_game.played == "closed":
                        active_games[stake_str] = {
                            "is_running": False,
                            "remaining_seconds": 0,
                            "winner_price": 0,
                            "bonus": has_bonus,
                        }
                    else:
                        active_games[stake_str] = {
                            "is_running": True,
                            "remaining_seconds": 0,
                            "winner_price": float(current_game.winner_price),
                            "bonus": has_bonus,
                        }

                elif next_game_start and next_game_start > current_timestamp:
                    remaining = int(next_game_start - current_timestamp)
                    no_p = int(self.redis_client.get(player_count_key) or 0)
                    winner = self.calculate_winner_price(no_p, stake)

                    active_games[stake_str] = {
                        "is_running": False,
                        "remaining_seconds": remaining,
                        "winner_price": winner,
                        "bonus": has_bonus,
                    }
                else:
                    active_games[stake_str] = {
                        "is_running": False,
                        "remaining_seconds": 0,
                        "winner_price": 0,
                        "bonus": has_bonus,
                    }

        except Exception as e:
            print(f"Error fetching active games: {e}")

        return active_games


    def safe_float(self, val):
        try:
            return float(val)
        except Exception:
            return 0.0

    def sanitize_data(self, data):
        from decimal import Decimal
        if isinstance(data, dict):
            return {k: self.sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_data(v) for v in data]
        elif isinstance(data, Decimal):
            return self.safe_float(data)
        else:
            return data

    def calculate_winner_price(self, no_p, stake):
        try:
            no_p = float(no_p)
            stake = float(stake)
            winner = no_p * stake

            if winner > 100:
                winner -= (winner * 0.2)

            # Optional: round to 2 decimal places
            winner = round(winner, 2)

            return winner

        except (ValueError, TypeError) as e:
            print(f"Error calculating winner price: {e}")
            return 0.0

    def broadcast_active_games(self):
        async_to_sync(self.channel_layer.group_send)(
            "game_all",
            {
                "type": "active_game_data",
                "data": self.get_all_active_games()
            }
        )

    # --- Player management ---
    def add_player(self, player_id, card_id):
        from custom_auth.models import User
        from decimal import Decimal

        selected_players = self.get_selected_players()

        # Remove existing entry for this user (if re-adding)
        selected_players = [p for p in selected_players if p['user'] != player_id]

        # Ensure card_id is a list
        card_ids = card_id if isinstance(card_id, list) else [card_id]

        # Get all used card IDs (excluding current user)
        used_cards = set()
        for player in selected_players:
            used_cards.update(player['card'])

        # Check if requested cards are already taken
        conflicting_cards = [cid for cid in card_ids if cid in used_cards]
        if conflicting_cards:
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': f"Card(s) already selected: {conflicting_cards}. Please choose different card(s)."
                }
            )
            return

        # User lookup and validation
        user = User.objects.get(id=player_id)
        if not user.is_active:
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'User account is inactive.'
                }
            )
            return

        total_cost = Decimal(self.stake) * len(card_ids)
        available_balance=user.wallet + user.bonus

        if available_balance< total_cost:
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Insufficient balance to join the game.'
                }
            )
            return

        # Add the player to the selection
        selected_players.append({'user': player_id, 'card': card_ids})
        self.set_selected_players(selected_players)

        # Update player count
        player_count = sum(len(p['card']) for p in selected_players)
        self.set_player_count(player_count)

        # Notify user
        self.send(text_data=json.dumps({
            "type": "success",
            "message": "card selected!",
            "card_ids": card_ids
        }))

        # Notify all players
        self.broadcast_player_list()

    def remove_player(self, player_id):
        selected_players = [p for p in self.get_selected_players() if p['user'] != player_id]
        self.set_selected_players(selected_players)
        self.set_player_count(sum(len(p['card']) for p in selected_players))
        self.send(text_data=json.dumps({
            "type": "player_removed",
            "user_id": player_id
        }))
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
                'stake': self.stake,
                'remaining_seconds': self.get_remaining_time()
            }
        )

        self.broadcast_active_games()
    
    def try_adding_random_players(self):
        from custom_auth.models import RandomPlayer
        from decimal import Decimal

        from decimal import Decimal, InvalidOperation

        try:
            # Normalize stake to a Decimal if possible
            if self.stake is None:
                return

            try:
                stake_value = Decimal(self.stake)
            except (InvalidOperation, TypeError):
                return

            random_player_config = RandomPlayer.objects.get(on_off=True, stake=stake_value)
        except RandomPlayer.DoesNotExist:
            return
        
        time.sleep(3)  # Initial delay before adding random players

        number_of_players = random_player_config.number_of_players
        # Randomize number of players within range (-6 to +5)
        number_of_players = random.randint(max(1, number_of_players - 3), number_of_players + 2)

        selection = 1
        if number_of_players >= 10:
            selection = 2

        for _ in range(number_of_players // selection):  # use integer division
            selected_players = self.get_selected_players()
            used_cards = set()
            next_game_start = self.get_stake_state("next_game_start")
            current_time = timezone.now()

            if next_game_start < current_time.timestamp():
                break

            for player in selected_players:
                used_cards.update(player['card'])

            card_ids = []
            while len(card_ids) < selection:  # each random player gets `selection` cards
                new_card_id = random.randint(1, 120)  # Adjust range as needed
                if new_card_id not in used_cards:
                    card_ids.append(new_card_id)
                    used_cards.add(new_card_id)

            selected_players.append({'user': 0, 'card': card_ids})
            self.set_selected_players(selected_players)
            self.broadcast_player_list()
            self.set_player_count(sum(len(p['card']) for p in selected_players))

            time.sleep(2)

        
    def try_start_game(self):
        from game.models import Game  # adjust this import if needed

        current_game_id = self.get_stake_state("current_game_id")
        current_time = timezone.now()

        is_running = self.get_game_state("is_running", current_game_id) if current_game_id else False
        next_game_start = self.get_stake_state("next_game_start")

        # ✅ Check if running game has expired
        if is_running and current_game_id:
            try:
                current_game = Game.objects.get(id=current_game_id)
                if current_game.started_at and (current_time - current_game.started_at).total_seconds() > 400:
                    # Game expired
                    current_game.played = "closed"  # assuming status is a string field
                    current_game.save(update_fields=["status"])
                    self.set_game_state("is_running", False, current_game_id)
                    current_game_id = None
                    self.set_stake_state("current_game_id", None)
            except Game.DoesNotExist:
                print(f"Game {current_game_id} not found.")

        # 🔁 Re-check if still running after timeout check
        if current_game_id and self.get_game_state("is_running", current_game_id):
            self.send(text_data=json.dumps({
                "type": "game_in_progress",
                "game_id": current_game_id
            }))
            return

        self.broadcast_active_games()

        # ✅ Start new game if no future schedule exists or time has passed
        if not next_game_start or next_game_start < current_time.timestamp():
            self.set_stake_state("next_game_start", current_time.timestamp() + 30)

            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'timer_message',
                    'remaining_seconds': 30,
                }
            )

            self.broadcast_active_games()

            def delayed_start():
                time.sleep(30)
                self._start_game_logic()

            threading.Thread(target=delayed_start, daemon=True).start()
            threading.Thread(target=self.try_adding_random_players, daemon=True).start()

    def _start_game_logic(self):
        from game.models import Game
        from django.utils import timezone

        selected_players = self.get_selected_players()
        if not selected_players or len(selected_players) < 2:
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'error',
                    'message': 'Not enough players selected. Cannot start game.'
                }
            )
            self.try_start_game()
            return

        player_card_map = {str(p['user']): p['card'] for p in selected_players}
        new_game = Game.objects.create(
            stake=self.stake,
            numberofplayers=sum(len(c) for c in player_card_map.values()),
            playerCard=player_card_map,
            random_numbers=json.dumps(self.generate_random_numbers()),
            winner_price=0,
            admin_cut=0,
            created_at=timezone.now(),
            started_at=timezone.now(),
            played='Started'
        )
        new_game.save()

        self.set_game_state("is_running", True, game_id=new_game.id)
        self.set_stake_state("current_game_id", new_game.id)

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

    # # --- Automatic Game Loop ---
    # def auto_game_start_loop(self):
    #     while True:
    #         selected_players = self.get_selected_players()
    #         player_count = self.get_player_count()
    #         active_games = self.get_active_games()

    #         print(f"Checking game start conditions: {player_count} players, {len(active_games)} active games")
    #         if len(active_games) < 2:
    #             from game.models import Game  # ✅ Make sure it's the correct path
    #             from django.utils import timezone

    #             self.set_stake_state("next_game_start", timezone.now().timestamp() + 30)

    #             async_to_sync(self.channel_layer.group_send)(
    #                 self.room_group_name,
    #                 {
    #                     'type': 'timer_message',
    #                     'remaining_seconds': 30,
    #                 }
    #             )

    #             time.sleep(30)  # Wait before checking again

    #             print("Starting a new game with selected players:", selected_players)
    #             # Build the playerCard map: {user_id: [card_ids]}
    #             player_card_map = {
    #                 str(p['user']): p['card'] for p in selected_players
    #             }

    #             # Calculate number of cards
    #             number_of_cards = sum(len(c) for c in player_card_map.values())

    #             # Create game in DB
    #             new_game = Game.objects.create(
    #                 stake=self.stake,
    #                 numberofplayers=number_of_cards,
    #                 playerCard=player_card_map,
    #                 random_numbers=json.dumps(self.generate_random_numbers()),
    #                 winner_price=0,  # Can be updated later
    #                 admin_cut=0,     # Can be calculated
    #                 created_at=timezone.now(),
    #                 started_at=timezone.now(),
    #                 played='Started'
    #             )
    #             new_game.save()
    #             print(f"New game created with ID: {new_game.id} and stake: {self.stake}")

    #             # Add game_id to Redis active games
    #             active_games.append(new_game.id)
    #             self.set_active_games(active_games)

    #             # Broadcast the game start
    #             async_to_sync(self.channel_layer.group_send)(
    #                 self.room_group_name,
    #                 {
    #                     'type': 'game_started',
    #                     'game_id': new_game.id,
    #                     'player_list': selected_players,
    #                     'stake': self.stake
    #                 }
    #             )

    #             print(f"Starting game with ID: {new_game.id} and players: {selected_players}")
    #             threading.Thread(
    #                 target=self.start_game_with_random_numbers,
    #                 args=(new_game, selected_players),
    #                 daemon=True
    #             ).start()
    #             print(f"Game thread started for game ID: {new_game.id}")
    #             # Reset players for new cycle
    #             self.set_selected_players([])
    #             self.set_player_count(0)
    #             self.broadcast_player_list()

    def get_remaining_time(self):
        next_start_ts = self.get_stake_state("next_game_start")
        if not next_start_ts:
            return 0
        now = time.time()
        remaining = max(0, int(next_start_ts - now))
        return remaining

    def generate_random_numbers(self):
        import secrets
        numbers = list(range(1, 76))
        # Fisher-Yates shuffle using cryptographic randomness
        for i in range(len(numbers) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            numbers[i], numbers[j] = numbers[j], numbers[i]
        return numbers

    def start_game_with_random_numbers(self, game, selected_players):
        from custom_auth.models import User, RandomPlayer
        from decimal import Decimal
        import json
        from game.models import Game, UserGameParticipation  # ✅ Import new model

        self.game_id = game.id
        self.set_game_state("is_running", True, game.id)
        self.set_game_state("bingo", False, game.id)

        game.played = 'Playing'
        game.save()

        random_player = RandomPlayer.objects.filter(stake=Decimal(self.stake)).first()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'playing',
                'game_id': game.id,
                'message': 'Game is now playing'
            }
        )

        stake_amount = Decimal(game.stake)
        updated_player_cards = []
        unique_entries = {}

        # Remove duplicate users: keep only last submitted entry per user
        for entry in selected_players:
            user_id = int(entry["user"])
            # Allow multiple entries for user 0
            if user_id == 0:
                # Just append separately for user 0
                unique_entries.setdefault("zero_users", []).append(entry)
            else:
                # Only keep one entry per unique user
                if user_id not in unique_entries:
                    unique_entries[user_id] = entry

        # Combine: user 0 entries + deduplicated others
        deduplicated_players = list(unique_entries.get("zero_users", [])) + [
            entry for key, entry in unique_entries.items() if key != "zero_users"
        ]

        for entry in deduplicated_players:
            try:
                if str(entry["user"]) == "0" or int(entry["user"]) == 0:
                    cards = entry["card"]
                    flat_cards = [c for sub in cards for c in sub] if isinstance(cards[0], list) else cards
                    total_deduction = stake_amount * len(flat_cards)
                    random_player.wallet -= total_deduction
                    random_player.save(update_fields=['wallet'])
                else:
                    user_id = entry["user"]
                    cards = entry["card"]
                    flat_cards = [c for sub in cards for c in sub] if isinstance(cards[0], list) else cards
                    total_deduction = stake_amount * len(flat_cards)
                    user = User.objects.get(id=user_id)

                    # ✅ STEP 1: Check combined balance (wallet + bonus)
                    available_balance = user.wallet + user.bonus
                    if available_balance < total_deduction:
                        self.remove_player(user_id)
                        continue

                    # ✅ STEP 2: Deduct from wallet first
                    remaining = total_deduction
                    if user.wallet >= remaining:
                        user.wallet -= remaining
                        remaining = Decimal('0')
                    else:
                        remaining -= user.wallet
                        user.wallet = Decimal('0')

                    # ✅ STEP 3: Deduct remaining from bonus
                    if remaining > 0:
                        user.bonus -= remaining

                    # ✅ STEP 4: Record user-game participation
                    participation, created = UserGameParticipation.objects.get_or_create(
                        user=user,
                        game=game,
                        defaults={'times_played': len(flat_cards)}
                    )
                    if not created:
                        participation.times_played = len(flat_cards)
                        participation.save(update_fields=['times_played'])

                    # ✅ STEP 5: Update user's total games played
                    try:
                        user.no_of_games_played = (user.no_of_games_played or 0) + 1
                    except AttributeError:
                        print(f"User {user_id} does not have 'no_of_games_played' field, skipping increment.")

                    user.save()

                entry["card"] = flat_cards
                updated_player_cards.append(entry)


            except Exception as e:
                self.remove_player(user_id)

        game.numberofplayers = sum(len(p['card']) for p in updated_player_cards)
        game.playerCard = updated_player_cards

        winner_price = stake_amount * game.numberofplayers

        if winner_price >= 100:
            admin_cut = winner_price * Decimal('0.2')  # 20%
            winner_price -= admin_cut
            game.admin_cut = admin_cut
        elif 50 <= winner_price < 100:
            admin_cut = winner_price * Decimal('0.1')  # 10%
            winner_price -= admin_cut
            game.admin_cut = admin_cut
        else:
            game.admin_cut = Decimal('0')

        game.winner_price = winner_price
        game.save()

        stake_value = int(self.stake or 0)
        if stake_value in [10, 20, 50] and game.numberofplayers >= 10:
            bonus_text = "10X"
        else:
            bonus_text = ""

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'game_stat',
                'number_of_players': game.numberofplayers,
                'stake': game.stake,
                'winner_price': float(game.winner_price),
                'bonus': bonus_text,
                'game_id': game.id,
                "is_running": True,
            }
        )

        time.sleep(5)
        # Broadcast random numbers every 4 seconds
        for num in json.loads(game.random_numbers):
            is_running = self.get_game_state("is_running", game.id)
            bingo = self.get_game_state("bingo", game.id)
            if not is_running or bingo:
                break

            with self.lock:
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'random_number',
                        'random_number': num,
                        'game_id': game.id
                    }
                )

                called = self.get_game_state("called_numbers", game.id) or []
                if not isinstance(called, list):
                    called = []
                called.append(num)
                self.set_game_state("called_numbers", called, game.id)

            time.sleep(2)
            
            self.checkBingoforRandomPlayers(called, game.id)

            time.sleep(2)

        game = Game.objects.get(id=game.id)
        game.played = 'closed'
        game.save()
        self.set_game_state("is_running", False, game.id)

        # Reset selection state
        self.set_selected_players([])
        self.set_player_count(0)
        self.broadcast_player_list()
        # self.regenerate_all_cards()
        self.try_start_game()
    
    def checkBingoforRandomPlayers(self, calledNumbers, game_id):
        from game.models import Card, Game
        from custom_auth.models import RandomPlayer, User

        game = Game.objects.get(id=int(game_id))
        selected_players = game.playerCard

        if game.winner or game.played == 'closed':
            return

        called_numbers_list = calledNumbers + [0]
        game.total_calls = len(called_numbers_list)
        game.save_called_numbers(called_numbers_list)
        game.save()

        # Check each random player's cards
        for entry in selected_players:
            if entry['user'] == 0:  # Random Player
                player_cards = entry['card']
                for card_id in player_cards:
                    try:
                        card = Card.objects.get(id=card_id)
                    except Card.DoesNotExist:
                        continue

                    numbers = json.loads(card.numbers)
                    winning_numbers = self.has_bingo(numbers, called_numbers_list)

                    if winning_numbers:
                        # Determine bones amount
                        random_player = RandomPlayer.objects.get(stake=self.stake)
                        stake = int(self.stake)
                        bones_amount = 0
                        if stake in [10, 20, 50] and game.numberofplayers >= 10:
                            bones = len(called_numbers_list)
                            if bones <= 5:
                                multiplier = 10
                            elif bones == 6:
                                multiplier = 8
                            elif bones == 7:
                                multiplier = 6
                            elif bones == 8:
                                multiplier = 4
                            elif bones == 9:
                                multiplier = 3
                            elif bones == 10:
                                multiplier = 2
                            elif bones == 11:
                                multiplier = 1
                            else:
                                multiplier = 0
                            bones_amount = stake * multiplier

                        # Check all real players for bingo
                        winners = self.check_bingo_for_all_players(game, called_numbers_list)

                        # Split prize among real users
                        total_win = game.winner_price + bones_amount
                        split_amount = total_win // max(len(winners), 1)
                        random_name = random.choice(random_player.names)

                        result = []
                        winner_ids = []

                        for w in winners:
                            if w['user_id'] == 0:
                                random_player.wallet += split_amount
                                random_ids = [217, 72, 173, 1, 170]
                                random_id = random.choice(random_ids)

                                winner_ids.append(random_id)
                                
                                random_player.save()
                                result.append({
                                    'user_id': random_id,
                                    'name': random_name,
                                    'card_id': w['card_id'],
                                    'card': w['card'],
                                    'winning_numbers': w['winning_numbers'],
                                    'amount_won': float(split_amount),
                                    'message': 'Bingo'
                                })
                            else:
                                winner_user = User.objects.get(id=w['user_id'])
                                winner_user.wallet += split_amount
                                winner_user.save()
                                winner_ids.append(w['user_id'])                                  
                                result.append({
                                    'user_id': winner_user.id,
                                    'name': winner_user.name,
                                    'card_id': w['card_id'],
                                    'card': w['card'],
                                    'winning_numbers': w['winning_numbers'],
                                    'amount_won': float(split_amount),
                                    'message': 'Bingo'
                                })

                        # Close game and save the actual caller's info
                        
                        game.played = "closed"
                        game.winner = winner_ids
                        game.winner_name = random_name
                        game.winner_card = card.id
                        game.bonus = bones_amount
                        game.save()

                        async_to_sync(self.channel_layer.group_send)(
                            self.room_group_name,
                            {
                                'type': 'result',
                                'data': result,
                                'game_id': game.id
                            }
                        )

                        self.set_game_state("bingo", True, game.id)
                        return

     # NEW HELPER: Update consecutive losses after game ends with a winner
    def update_consecutive_losses_after_game(self, game_id, winner_user_id):
            from custom_auth.models import User
            from game.models import UserGameParticipation

            # Get all user IDs who participated in this game
            participant_user_ids = UserGameParticipation.objects.filter(game_id=game_id).values_list('user_id',
                                                                                                     flat=True)
            for user_id in participant_user_ids:
                try:
                    user = User.objects.get(id=user_id)
            
                    # Ensure defaults for safety
                    if user.consecutive_losses is None:
                        user.consecutive_losses = 0
                    if user.bonus is None:
                        user.bonus = 0
            
                    if user_id == winner_user_id:
                        # Winner: reset loss streak
                        user.consecutive_losses = 0
                        user.save(update_fields=['consecutive_losses'])
                    else:
                        user.consecutive_losses += 1
                        if user.consecutive_losses >= 10:
                            user.bonus += 10
                            user.consecutive_losses = 0
                            user.save(update_fields=['bonus', 'consecutive_losses'])
                        else:
                            user.save(update_fields=['consecutive_losses'])
            
                except User.DoesNotExist:
                    continue

    def checkBingo(self, user_id, calledNumbers, game_id):
        from game.models import Card, Game
        from custom_auth.models import User

        game = Game.objects.get(id=int(game_id))
        result = []

        # Retrieve player's cards based on the provided user_id
        selected_players = game.playerCard
        players = selected_players
        player_cards = [entry['card'] for entry in players if int(entry['user']) == int(user_id)]

        if not player_cards:
            # User does not have any cards associated
            result.append({'user_id': user_id, 'message': 'Not a Player'})
            self.send(text_data=json.dumps({
                'type': 'result',
                'data': result,
                'game_id': game.id,
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

        if game.winner:
            return

        if game.played == 'closed':
            return

            # Include a zero at the end of the called numbers (for "free space" if applicable)
        # if not set(calledNumbers).issubset(self.get_game_state("called_numbers",game.id) or []):
        #     print("Called numbers do not match the game's called numbers.")
        #     return

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

        # Loop through all the cards assigned to the user
        for card in cards:
            numbers = json.loads(card.numbers)
            # Check if this card has a Bingo with the called numbers
            winning_numbers = self.has_bingo(numbers, called_numbers_list)

            if winning_numbers:

                if game.played == "closed":
                    return

                # ---- CHECK ALL PLAYERS ----
                winners = self.check_bingo_for_all_players(game, called_numbers_list)

                # Get stake amount (assuming game.stake or similar field exists)
                stake = game.stake
                bones_amount = 0

                if stake in [10, 20, 50] and game.numberofplayers >= 10:
                    bones = len(called_numbers_list)

                    if bones <= 5:
                        multiplier = 10
                    elif bones == 6:
                        multiplier = 8
                    elif bones == 7:
                        multiplier = 6
                    elif bones == 8:
                        multiplier = 4
                    elif bones == 9:
                        multiplier = 3
                    elif bones == 10:
                        multiplier = 2
                    elif bones == 11:
                        multiplier = 1
                    else:
                        multiplier = 0

                    bones_amount = stake * multiplier

                # ---- SPLIT AMOUNT ----
                total_win = game.winner_price + bones_amount
                split_amount = total_win // len(winners)

                result = []

                for w in winners:
                    if w['user_id'] == 0:
                        continue  # Skip random player here

                    user = User.objects.get(id=w['user_id'])
                    user.wallet += split_amount
                    user.save()

                    result.append({
                        'user_id': user.id,
                        'name': user.name,
                        'card_id': w['card_id'],
                        'card': w['card'],
                        'winning_numbers': w['winning_numbers'],
                        'amount_won': float(split_amount),
                        'message': 'Bingo',
                    })

                winner_ids = [w['user_id'] for w in winners]

                # ---- CLOSE GAME ----
                game.played = "closed"
                game.winner = winner_ids
                game.winner_name = user.name
                game.winner_card = card.id
                game.bonus = bones_amount
                game.save()

                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'result',
                        'data': result,
                        'game_id': game.id
                    }
                )

                self.set_game_state("bingo", True, game.id)
                return


        # If no Bingo was found for any card
        result.append({
            'user_id': user_id,
            'message': 'No Bingo',
            'cards_checked': player_cards,
            'called_numbers': called_numbers_list
        })
        self.send(text_data=json.dumps({
            'type': 'result',
            'data': result,
            'game_id': game.id
        }))
    
    def check_bingo_for_all_players(self, game, called_numbers):
        from game.models import Card
        from custom_auth.models import User

        winners = []

        for entry in game.playerCard:
            user_id = int(entry['user'])
            card_ids = entry['card']

            cards = Card.objects.filter(id__in=card_ids)

            for card in cards:
                numbers = json.loads(card.numbers)
                winning_numbers = self.has_bingo(numbers, called_numbers)

                if winning_numbers:
                    if user_id == 0:
                        winners.append({
                            'user_id': 0,
                            'name': 'Random Player',
                            'card_id': card.id,
                            'card': numbers,
                            'winning_numbers': winning_numbers,
                        })
                        break  # one winning card per user is enough
                    else:
                        user = User.objects.get(id=user_id)
                        winners.append({
                            'user_id': user.id,
                            'name': user.name,
                            'card_id': card.id,
                            'card': numbers,
                            'winning_numbers': winning_numbers,
                        })
                        break  # one winning card per user is enough

        return winners

    def has_bingo(self, card, called_numbers):
        winning_columns = 0
        corner_count = 0
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

        inner_corner_count = 0
        # Check the top-left corner (1, 1)
        if card[1][1] in called_numbers:
            inner_corner_count += 1

        # Check the top-right corner (1, 5)
        if card[1][3] in called_numbers:
            inner_corner_count += 1

        # Check the bottom-left corner (5, 1)
        if card[3][1] in called_numbers:
            inner_corner_count += 1

        # Check the bottom-right corner (5, 5)
        if card[3][3] in called_numbers:
            inner_corner_count += 1

        if inner_corner_count == 4:
            winning_numbers.extend([7, 9, 17, 19])

        return winning_numbers

    def block(self, user_id):
        from game.models import Game
        current_game_id = self.get_stake_state("current_game_id")
        if not current_game_id:
            return
        last_game = Game.objects.get(id=current_game_id)
        players = last_game.playerCard
        updated_list = [item for item in players if int(item['user']) != user_id]
        last_game.playerCard = json.dumps(updated_list)
        last_game.numberofplayers = len(updated_list)
        last_game.save()

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
            'stake': event['stake'],
            'winner_price': event.get('winner_price', 0),
            'bonus': event.get('bonus', ""),
            'game_id': event.get('game_id', None),
            'is_running': event.get('is_running', False),
            'remaining_seconds': event.get('remaining_seconds', 0),
            'called_numbers': event.get('called_numbers', [])
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

    def random_number(self, event):
        self.send(text_data=json.dumps({
            'type': 'random_number',
            'random_number': event['random_number'],
            'game_id': event['game_id']
        }))

    def timer_message(self, event):
        self.send(text_data=json.dumps({
            'type': 'timer_message',
            'remaining_seconds': event['remaining_seconds'],
        }))

    def playing(self, event):
        self.send(text_data=json.dumps({
            'type': 'playing',
            'game_id': event['game_id'],
            'message': event['message']
        }))

    def game_stats(self, event):
        self.send(text_data=json.dumps({
            'type': 'game_stats',
            'number_of_players': event['number_of_players'],
            'stake': event['stake'],
            'winner_price': event['winner_price'],
            'bonus': event['bonus'],
            'game_id': event['game_id']
        }))

    def result(self, event):
        self.send(text_data=json.dumps({
            'type': 'result',
            'data': event['data'],
            'game_id': event['game_id']
        }))

    def no_cards(self, event):
        self.send(text_data=json.dumps({
            'type': 'no_cards',
            'message': event['message']
        }))

    def active_game_data(self, event):
        self.send(text_data=json.dumps({
            'type': 'active_game_data',
            'data': event['data']
        }))
