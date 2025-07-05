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

        elif data['type'] == 'remove_number':
            self.remove_player(data['userId'])

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

                # Reset players for new cycle
                self.set_selected_players([])
                self.set_player_count(0)

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
