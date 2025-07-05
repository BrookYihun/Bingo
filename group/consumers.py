import json
import threading
from django.utils import timezone
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
import redis
from game.models import Game
from group.models import GroupGame  # Import your linking model


class GroupConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)
        self.lock = threading.Lock()
        self.active_games = {}

    def connect(self):
        self.group_id = self.scope['url_route']['kwargs']['group_id']
        self.room_group_name = f"group_{self.group_id}"

        try:
            group_game = GroupGame.objects.select_related('game').get(group__id=int(self.group_id))
            self.game = group_game.game
            self.game_id = self.game.id  # So you can reuse GameConsumer logic

            if self.game.played == 'closed':
                self.accept()
                self.send(text_data=json.dumps({
                    'type': 'game_expired',
                    'groupId': self.group_id
                }))
                self.close()
                return

            self.accept()

            # Reuse GameConsumer logic here
            self.handle_game_state()

            async_to_sync(self.channel_layer.group_add)(
                self.room_group_name,
                self.channel_name
            )

        except GroupGame.DoesNotExist:
            self.close()

    def handle_game_state(self):
        # Simplified logic example from your GameConsumer
        if self.game.played == 'Playing':
            self.send(text_data=json.dumps({
                'type': 'called_numbers',
                'called_numbers': self.get_game_state("called_numbers") or []
            }))
        
        if self.game.played == 'Started':
            if self.get_player_count() == 0:
                self.game.played = 'Created'
                self.game.started_at = None
                self.game.save()
                self.set_game_state("is_running", False)
                self.set_game_state("bingo", False)
                return

            start_delay = 29
            start_time_with_delay = self.game.started_at + timezone.timedelta(seconds=start_delay)
            now = timezone.now()
            remaining = (start_time_with_delay - now).total_seconds()
            remaining_seconds = max(int(remaining), 0)

            if remaining < 0:
                self.close()
                return

            self.send(text_data=json.dumps({
                'type': 'timer_message',
                'remaining_seconds': remaining_seconds,
                'message': str(self.game.started_at),
            }))

        # Add any other game state init logic...

    def get_game_state(self, key):
        redis_key = f"game_state_{self.game_id}"
        state = self.redis_client.hget(redis_key, key)
        return json.loads(state) if state else None

    def set_game_state(self, key, value):
        redis_key = f"game_state_{self.game_id}"
        self.redis_client.hset(redis_key, key, json.dumps(value))

    def get_player_count(self):
        count = self.redis_client.get(f"player_count_{self.game_id}")
        return int(count) if count else 0

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'game_start':
            self.start_game()

    def start_game(self):
        if self.game.played == "Created" and self.get_player_count() > 1:
            self.game.started_at = timezone.now()
            self.game.played = 'Started'
            self.game.save()
            self.set_game_state("is_running", True)

            self.send(text_data=json.dumps({
                'type': 'timer_message',
                'remaining_seconds': 29,
                'message': str(self.game.started_at),
            }))

            thread = threading.Thread(target=self.send_random_numbers_periodically)
            thread.start()

    def send_random_numbers_periodically(self):
        import json
        import time
        from decimal import Decimal
        from game.models import Game
        from custom_auth.models import User

        game = self.game  # Already set in connect()
        is_running = self.get_game_state("is_running")

        start_delay = 29
        start_time_with_delay = game.started_at + timezone.timedelta(seconds=start_delay)

        now = timezone.now()
        remaining = (start_time_with_delay - now).total_seconds()
        remaining_seconds = max(int(remaining), 0)

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'timer_message',
                'remaining_seconds': remaining_seconds,
                'message': str(game.started_at),
            }
        )

        time.sleep(30)  # wait before playing
        game.played = 'Playing'
        game.save()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'playing',
                'message': 'game is now playing'
            }
        )

        stake_amount = Decimal(game.stake)
        selected_players = self.get_selected_players()
        players = selected_players
        total_cards = sum(len(player["card"]) for player in players)
        game.numberofplayers = int(total_cards)
        winner_price = total_cards * int(game.stake)

        if winner_price >= 100:
            admin_cut = winner_price * 0.2
            winner_price = winner_price - admin_cut
            game.admin_cut = admin_cut

        game.winner_price = winner_price

        bingo_page_users = self.get_bingo_page_users()
        updated_player_cards = []

        for entry in players:
            try:
                user_id = entry["user"]
                cards = entry["card"]

                flattened_cards = [card_id for sublist in cards for card_id in sublist] if isinstance(cards[0], list) else cards
                num_cards = len(flattened_cards)
                total_deduction = stake_amount * num_cards

                user = User.objects.get(id=user_id)

                if user_id in bingo_page_users:
                    if user.wallet >= total_deduction:
                        user.wallet -= total_deduction
                        user.save()
                        entry["card"] = flattened_cards
                        updated_player_cards.append(entry)
                    else:
                        self.remove_player(user_id)
                else:
                    print(f"User {user_id} is not on the bingo page.")
                    self.remove_player(user_id)

            except User.DoesNotExist:
                print(f"User with id {user_id} not found.")
            except Exception as e:
                print(f"Error processing deduction: {e}")

        game.playerCard = json.dumps(updated_player_cards)
        game.save()

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'game_stats',
                'number_of_players': self.get_player_count(),
                'stake': game.stake,
                'winner_price': game.winner_price,
                'bonus': game.bonus,
            }
        )

        for num in self.game_random_numbers:
            is_running = self.get_game_state("is_running")
            if not is_running:
                break

            with self.lock:
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'random_number',
                        'random_number': num
                    }
                )

                called = self.get_game_state("called_numbers") or []
                if not isinstance(called, list):
                    called = []
                called.append(num)
                self.set_game_state("called_numbers", called)

            time.sleep(5)

        time.sleep(10)
        game.played = 'closed'
        game.save()
        self.set_game_state("is_running", False)

        if self.game_id in self.active_games:
            del self.active_games[self.game_id]

        self.close()

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
            'remaining_seconds': event['remaining_seconds'],
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

    def block(self, user_id):
        from game.models import Game
        last_game = Game.objects.get(id=self.game_id)
        players = json.loads(last_game.playerCard)
        updated_list = [item for item in players if int(item['user']) != user_id]
        last_game.playerCard = json.dumps(updated_list)
        last_game.numberofplayers = len(updated_list)
        last_game.save()

    def add_player(self, player_id, card_id):
        from custom_auth.models import User
        from decimal import Decimal
        from django.utils import timezone
        from django.db.models import Q
        from game.models import Game

        game = self.game  # Already set in connect()
        now = timezone.now()

        # Step 1: Get games with specific statuses
        active_games_qs = Game.objects.filter(played__in=['Started', 'Created', 'Playing'])

        # Step 2: Define expiration conditions
        expired_games = active_games_qs.filter(
            Q(played='Created', started_at__lt=now - timezone.timedelta(seconds=30)) |
            Q(played='Started', started_at__lt=now - timezone.timedelta(seconds=30)) |
            Q(played='Playing') & (Q(started_at__lt=now - timezone.timedelta(seconds=375)))
        )

        # Step 3: Close expired games
        expired_games.update(played='closed')

        # ✅ Check for other active games with same stake
        active_games_with_same_stake = Game.objects.filter(
            stake=game.stake,
            played='Playing',
            numberofplayers__gt=2
        ).exclude(id=game.id).count()

        if active_games_with_same_stake > 2:
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Please wait: Maximum number of active games for this stake is reached.'
                }
            )
            return

        # ❗ Disallow joining if already in progress
        if game.played == "playing":
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Cannot join: The game is already in progress.'
                }
            )
            return

        # ✅ Update selected players
        selected_players = self.get_selected_players()
        print(f"[add_player][before] For game {self.game_id}: {selected_players}")
        
        selected_players = [p for p in selected_players if p['user'] != player_id]

        card_ids = card_id if isinstance(card_id, list) else [card_id]
        selected_players.append({'user': player_id, 'card': card_ids})
        print(f"[add_player][after append] For game {self.game_id}: {selected_players}")
        self.set_selected_players(selected_players)

        # ✅ Update count in Redis
        player_count = sum(len(p['card']) if isinstance(p['card'], list) else 1 for p in selected_players)
        self.set_player_count(player_count)

        # ✅ Balance Check
        user = User.objects.get(id=player_id)
        total_cost = Decimal(game.stake) * len(card_ids)

        if user.wallet < total_cost:
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'error',
                    'message': 'Insufficient balance to join the game.'
                }
            )
            return

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
                'player_list': self.get_selected_players()
            }
        )

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'game_stat',
                'number_of_players': self.get_player_count(),
                'stake': game.stake,
            }
        )
    
    def remove_player(self, player_id):
        game = self.game  # Use already loaded game object

        selected_players = self.get_selected_players()
        print(f"[remove_player][before] For game {self.game_id}: {selected_players}")
        selected_players = [p for p in selected_players if p['user'] != player_id]
        print(f"[remove_player][after remove] For game {self.game_id}: {selected_players}")
        self.set_selected_players(selected_players)

        player_count = sum(len(p['card']) if isinstance(p['card'], list) else 1 for p in selected_players)
        self.set_player_count(player_count)

        if player_count == 0:
            game.played = 'Created'
            game.started_at = None
            game.save()
            self.set_game_state("is_running", False)
            self.set_game_state("bingo", False)

        # Notify group of player update
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
                'stake': game.stake or 0,
            }
        )

    def update_player_list(self, event):
        self.send(text_data=json.dumps({
            'type': 'player_list',
            'player_list': event['player_list']
        }))

    def error(self, event):
        self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message']
        }))

    def sucess(self, event):
        self.send(text_data=json.dumps({
            'type': 'sucess',
            'message': event['message']
        }))

    def game_stat(self, event):
        self.send(text_data=json.dumps({
            'type': 'game_stat',
            'number_of_players': event['number_of_players'],
            'stake': event['stake']
        }))

    def game_stats(self, event):
        self.send(text_data=json.dumps({
            'type': 'game_stats',
            'number_of_players': event['number_of_players'],
            'stake': event['stake'],
            'winner_price': event['winner_price'],
            'bonus': event['bonus']
        }))
