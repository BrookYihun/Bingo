import json
import os
import threading
import time
import random
from decimal import Decimal, InvalidOperation
import uuid
import redis

from django.utils import timezone
from asgiref.sync import async_to_sync

from game.models import Game, Card
from custom_auth.models import User, RandomPlayer


REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
channel_layer = None  
room_group_name = "game_all"
stake = 10

def publish_event(stake, event, target_client_id=None):
    """
    Publish an event to Redis.
    Only ONE worker is allowed to broadcast this event.
    """
    ch = f"game:{stake}:events"
    
    # Unique lock key for this stake & event type
    event_type = event.get("type", "unknown")
    lock_key = f"broadcast_lock:{stake}:{event_type}"
    
    # Unique token for safe lock release
    lock_token = str(uuid.uuid4())

    # Try to acquire lock (NX = only if not exists)
    got_lock = r.set(lock_key, lock_token, nx=True, ex=1)  
    # ex=1 ensures lock auto-expires after 1 second

    if not got_lock:
        # another worker already broadcasting this event
        return  

    # Prepare payload
    payload = {
        "event": event,
        "target_client_id": target_client_id
    }

    # Publish to Redis channel
    r.publish(ch, json.dumps(payload))

    # Safely release lock ONLY if we still own it
    try:
        release_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        r.eval(release_script, 1, lock_key, lock_token)
    except Exception:
        pass

# --- Redis state helpers ---
class RedisState:
    def __init__(self, redis_client, stake):
        self.redis_client = redis_client
        self.stake = stake


    # --- Player selection ---
    def get_selected_players(self):
        key = f"selected_players_{self.stake}"
        data = self.redis_client.get(key)
        return json.loads(data) if data else []

    def set_selected_players(self, players):
        key = f"selected_players_{self.stake}"
        self.redis_client.set(key, json.dumps(players))

    # --- Player count ---
    def get_player_count(self):
        return int(self.redis_client.get(f"player_count_{self.stake}") or 0)

    def set_player_count(self, count):
        self.redis_client.set(f"player_count_{self.stake}", count)

    # --- Game state ---
    def get_game_state(self, key, game_id):
        val = self.redis_client.get(f"game_state_{game_id}_{key}")
        return json.loads(val) if val else None

    def set_game_state(self, key, value, game_id):
        self.redis_client.set(f"game_state_{game_id}_{key}", json.dumps(value))
    
    def save_game_data(self, game):
        """
        Save full game metadata to Redis.
        Used by game engine; DB worker can persist later.
        """
        key = f"game_data:{game.id}"

        payload = {
            "game_id": game.id,
            "stake": game.stake,
            "numberofplayers": game.numberofplayers,
            "playerCard": game.playerCard,
            "random_numbers": json.loads(game.random_numbers),
            "winner_price": float(game.winner_price),
            "admin_cut": float(game.admin_cut),
            "played": game.played,
            "created_at": game.created_at.isoformat() if game.created_at else None,
            "started_at": game.started_at.isoformat() if game.started_at else None,
        }

        self.redis_client.set(key, json.dumps(payload))
    
    def get_game_data(self, game_id):
        key = f"game_data:{game_id}"
        val = self.redis_client.get(key)
        return json.loads(val) if val else None

    # --- Stake state ---
    def get_stake_state(self, key):
        val = self.redis_client.get(f"stake_state_{self.stake}_{key}")
        return json.loads(val) if val else None

    def set_stake_state(self, key, value):
        self.redis_client.set(f"stake_state_{self.stake}_{key}", json.dumps(value))

    # --- Bingo page users ---
    def get_bingo_page_users(self):
        data = self.redis_client.get(f"bingo_page_users_{self.stake}")
        return set(json.loads(data)) if data else set()

    def set_bingo_page_users(self, users):
        self.redis_client.set(f"bingo_page_users_{self.stake}", json.dumps(list(users)))
    
    def get_remaining_time(self):
        next_start_ts = self.get_stake_state("next_game_start")
        if not next_start_ts:
            return 0
        now = time.time()
        remaining = max(0, int(next_start_ts - now))
        return remaining

    # --- End game ---
    def end_game(self, game_id):
        self.set_game_state("is_running", False, game_id=game_id)
        self.set_stake_state("current_game_id", None)

    # --- Winner price calculation ---
    def calculate_winner_price(self, no_p, stake):
        try:
            no_p = float(no_p)
            stake = float(stake)
            winner = no_p * stake
            if winner > 100:
                winner -= (winner * 0.2)
            return round(winner, 2)
        except (ValueError, TypeError):
            return 0.0

    # --- Active games ---
    def get_all_active_games(self):
        active_games = {}
        stakes = [10, 20, 30, 40, 50, 100, 150, 200]
        bonus_stakes = {10, 20, 50}

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

            is_running = self.get_game_state("is_running", current_game_id) if current_game_id else False
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
        return active_games
    
    def broadcast_active_games(self):
        publish_event(
            stake="all",
            event={
                "type": "active_game_data",
                "data": self.get_all_active_games()
            }
        )

    
    def broadcast_player_list(self):
        # Send player list update
        publish_event(
            stake=self.stake,
            event={
                "type": "player_list",
                "player_list": self.get_selected_players()
            }
        )

        # Send player/game stats
        publish_event(
            stake=self.stake,
            event={
                "type": "game_stat",
                "number_of_players": self.get_player_count(),
                "stake": self.stake,
                "remaining_seconds": self.get_remaining_time()
            }
        )

        # Update the “all stakes” overview
        self.broadcast_active_games()

class GameManager:
    def __init__(self, redis_state: RedisState, stake, room_group_name, client_id=None):
        """
        redis_state: instance of RedisState with redis_client and helper methods
        stake: stake (str or int)
        room_group_name: e.g. "game_10"
        client_id: the Twisted client_id to target single-client events
        """
        self.redis_state = redis_state
        self.stake = str(stake)
        self.room_group_name = room_group_name
        self.client_id = client_id
        self.lock = threading.Lock()

    # ---- internal publish helper (uses redis pubsub format your Twisted server expects) ----
    def _publish(self, event, target_client_id=None, room_name=None):
        payload = {
            "event": event
        }
        if target_client_id is not None:
            payload["target_client_id"] = target_client_id
        if room_name:
            payload["room_name"] = room_name
        ch = f"game:{self.stake}:events"
        r.publish(ch, json.dumps(payload))
    
    # ---- player management ----
    def add_player(self, payload):
        """
        payload expected keys: player_id, card_id
        Returns an event dict (optional), or None.
        """
        player_id = payload.get("player_id")
        card_id = payload.get("card_id")

        # validate
        if player_id is None or card_id is None:
            self._publish(
                {"type": "error", "message": "player_id and card_id required"},
                target_client_id=self.client_id
            )
            return

        # check running
        current_game_id = self.redis_state.get_stake_state("current_game_id")
        is_running = self.redis_state.get_game_state("is_running", current_game_id) if current_game_id else False
        if is_running:
            self._publish(
                {"type": "error", "message": "Game already in progress. Please wait for next round."},
                target_client_id=self.client_id
            )
            return

        # load/set selected players
        selected_players = self.redis_state.get_selected_players()
        selected_players = [p for p in selected_players if p["user"] != player_id]

        card_ids = card_id if isinstance(card_id, list) else [card_id]

        used_cards = set()
        for p in selected_players:
            # handle nested lists
            for c in (p.get("card") or []):
                if isinstance(c, list):
                    used_cards.update(c)
                else:
                    used_cards.add(c)

        conflicts = [c for c in card_ids if c in used_cards]
        if conflicts:
            self._publish(
                {"type": "error", "message": f"Card(s) already selected: {conflicts}"},
                target_client_id=self.client_id
            )
            return

        # validate user & balance
        try:
            user = User.objects.get(id=player_id)
        except User.DoesNotExist:
            self._publish({"type":"error","message":"User not found"}, target_client_id=self.client_id)
            return

        if not user.is_active:
            self._publish({"type":"error","message":"User account is inactive."}, target_client_id=self.client_id)
            return

        try:
            stake_decimal = Decimal(int(self.stake))
        except:
            self._publish({"type":"error","message":"Invalid stake."}, target_client_id=self.client_id)
            return

        total_cost = stake_decimal * len(card_ids)

        if (user.wallet + user.bonus) < total_cost:
            self._publish({"type":"error","message":"Insufficient balance."}, target_client_id=self.client_id)
            return

        # all good → update redis state
        selected_players.append({"user": int(player_id), "card": card_ids})
        self.redis_state.set_selected_players(selected_players)
        self.redis_state.set_player_count(sum(len(p["card"]) for p in selected_players))

        # send success only to this client (but include player_list so client can update UI)
        self._publish({
            "type": "add_player_success",
            "player_list": selected_players
        }, target_client_id=self.client_id)

        # Also broadcast updated player_list to everyone (no target_client_id)
        self._publish({
            "type": "player_list",
            "player_list": selected_players
        }, target_client_id=None)

    def remove_player(self, payload):
        """payload expects player_id"""
        player_id = payload.get("userId")
        if player_id is None:
            self._publish({"type":"error","message":"player_id required"}, target_client_id=self.client_id)
            return

        selected_players = [p for p in self.redis_state.get_selected_players() if p["user"] != int(player_id)]
        self.redis_state.set_selected_players(selected_players)
        self.redis_state.set_player_count(sum(len(p["card"]) for p in selected_players))

        # Notify the caller and broadcast player_list
        self._publish({"type":"player_removed","user_id": player_id}, target_client_id=self.client_id)
        self._publish({"type":"player_list","player_list": selected_players}, target_client_id=None)

    # ---- start game scheduling ----
    def try_start_game(self):
        current_game_id = self.redis_state.get_stake_state("current_game_id")
        current_time = timezone.now()
        is_running = self.redis_state.get_game_state("is_running", current_game_id) if current_game_id else False
        next_game_start = self.redis_state.get_stake_state("next_game_start")

        # expire old running games
        if is_running and current_game_id:
            try:
                current_game = self.redis_state.get_game_data(current_game_id)
                if not current_game:
                    current_game = Game.objects.get(id=current_game_id)
                if current_game.started_at and (current_time - current_game.started_at).total_seconds() > 400:
                    current_game.played = "closed"
                    current_game.save(update_fields=["played"])
                    self.redis_state.set_game_state("is_running", False, current_game_id)
                    current_game_id = None
                    self.redis_state.set_stake_state("current_game_id", None)
            except Game.DoesNotExist:
                pass

        # if already running just return
        if current_game_id and self.redis_state.get_game_state("is_running", current_game_id):
            return None

        # schedule next game if none
        if not next_game_start or next_game_start < current_time.timestamp():
            self.redis_state.set_stake_state("next_game_start", current_time.timestamp() + 30)
            # inform clients about countdown
            self._publish({"type":"timer_message", "remaining_seconds":30}, target_client_id=None)
            self.redis_state.broadcast_active_games()
            # start actual start in background
            threading.Thread(target=self._delayed_start, daemon=True).start()
            # also try adding random players
            threading.Thread(target=self.try_adding_random_players, daemon=True).start()
            return {"type":"scheduled_start","remaining_seconds":30}
        return None

    def _delayed_start(self):
        time.sleep(30)
        self._start_game_logic()

    def _start_game_logic(self):
        selected_players = self.redis_state.get_selected_players()
        if not selected_players or len(selected_players) < 2:
            # broadcast not enough players
            self._publish({"type":"error","message":"Not enough players to start"}, target_client_id=None)
            # reset schedule and keep trying
            self.try_start_game()
            return

        # create game
        player_card_map = {str(p["user"]): p["card"] for p in selected_players}
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

        self.redis_state.save_game_data(new_game)

        self.redis_state.set_game_state("is_running", True, game_id=new_game.id)
        self.redis_state.set_stake_state("current_game_id", new_game.id)

        # broadcast game started
        self._publish({
            "type":"game_started",
            "game_id": new_game.id,
            "player_list": selected_players,
            "stake": self.stake
        }, target_client_id=None)

        # start number broadcaster thread
        threading.Thread(target=self.start_game_with_random_numbers, args=(new_game, selected_players), daemon=True).start()

    def generate_random_numbers(self):
        import secrets
        numbers = list(range(1, 76))
        for i in range(len(numbers) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            numbers[i], numbers[j] = numbers[j], numbers[i]
        return numbers

    # ---- random players ----
    def try_adding_random_players(self):
        try:
            rp = RandomPlayer.objects.filter(on_off=True, stake=Decimal(self.stake)).first()
        except Exception:
            return
        if not rp:
            return
        time.sleep(3)
        number_of_players = rp.number_of_players
        number_of_players = random.randint(max(1, number_of_players - 3), number_of_players + 2)
        selection = 2 if number_of_players >= 10 else 1
        for _ in range(number_of_players // selection):
            selected_players = self.redis_state.get_selected_players()
            used = set()
            for p in selected_players:
                for c in p.get("card", []):
                    if isinstance(c, list):
                        used.update(c)
                    else:
                        used.add(c)
            card_ids = []
            while len(card_ids) < selection:
                candidate = random.randint(1, 120)
                if candidate not in used:
                    card_ids.append(candidate)
                    used.add(candidate)
            selected_players.append({"user": 0, "card": card_ids})
            self.redis_state.set_selected_players(selected_players)
            # broadcast using redis format
            self._publish({"type":"player_list","player_list":selected_players}, target_client_id=None)
            self.redis_state.set_player_count(sum(len(p["card"]) for p in selected_players))
            time.sleep(2)

    # ---- number broadcast + game finish ----
    def start_game_with_random_numbers(self, game, selected_players):
        # similar to your previous implementation but using _publish for events
        self.redis_state.set_game_state("is_running", True, game.id)
        self.redis_state.set_game_state("bingo", False, game.id)

        game.played = "Playing"
        game.save()

        stake_amount = Decimal(game.stake)
        updated_player_cards = []

        # deduplicate entries (keep last)
        unique = {}
        zeros = []
        for e in selected_players:
            if int(e["user"]) == 0:
                zeros.append(e)
            else:
                unique[e["user"]] = e
        dedup = zeros + list(unique.values())

        # handle deductions and build updated_player_cards
        for entry in dedup:
            try:
                if int(entry["user"]) == 0:
                    cards = entry["card"]
                    flat = [c for sub in cards for c in sub] if isinstance(cards[0], list) else cards
                    # deduct from RandomPlayer wallet
                    rp = RandomPlayer.objects.filter(stake=Decimal(self.stake)).first()
                    if rp:
                        rp.wallet -= stake_amount * len(flat)
                        rp.save(update_fields=["wallet"])
                else:
                    uid = int(entry["user"])
                    cards = entry["card"]
                    flat = [c for sub in cards for c in sub] if isinstance(cards[0], list) else cards
                    user = User.objects.get(id=uid)
                    total = stake_amount * len(flat)
                    avail = user.wallet + user.bonus
                    if avail < total:
                        # remove player due to insufficient funds
                        continue
                    remaining = total
                    if user.wallet >= remaining:
                        user.wallet -= remaining
                        remaining = Decimal("0")
                    else:
                        remaining -= user.wallet
                        user.wallet = Decimal("0")
                    if remaining > 0:
                        user.bonus -= remaining
                    user.save()
                entry["card"] = flat
                updated_player_cards.append(entry)
            except Exception:
                # skip problematic entry
                continue

        game.numberofplayers = sum(len(p["card"]) for p in updated_player_cards)
        game.playerCard = updated_player_cards

        winner_price = stake_amount * game.numberofplayers
        if winner_price >= 100:
            admin_cut = winner_price * Decimal("0.2")
            winner_price -= admin_cut
            game.admin_cut = admin_cut
        elif 50 <= winner_price < 100:
            admin_cut = winner_price * Decimal("0.1")
            winner_price -= admin_cut
            game.admin_cut = admin_cut
        else:
            game.admin_cut = Decimal("0")
        game.winner_price = winner_price
        game.save()

        bonus_text = "10X" if int(self.stake) in (10, 20, 50) and game.numberofplayers >= 10 else ""

        # broadcast game_stat
        self._publish({
            "type": "game_stat",
            "number_of_players": game.numberofplayers,
            "stake": game.stake,
            "winner_price": float(game.winner_price),
            "bonus": bonus_text,
            "game_id": game.id,
            "is_running": True
        }, target_client_id=None)

        time.sleep(5)
        # draw numbers
        numbers = json.loads(game.random_numbers)
        for num in numbers:
            # stop conditions
            is_running = self.redis_state.get_game_state("is_running", game.id)
            bingo_flag = self.redis_state.get_game_state("bingo", game.id)
            if not is_running or bingo_flag:
                break

            with self.lock:
                # broadcast number
                self._publish({"type":"random_number","random_number":num,"game_id":game.id}, target_client_id=None)
                called = self.redis_state.get_game_state("called_numbers", game.id) or []
                if not isinstance(called, list):
                    called = []
                called.append(num)
                self.redis_state.set_game_state("called_numbers", called, game.id)

            # allow random players check
            time.sleep(2)
            self.check_bingo_for_random_players(called, game)
            time.sleep(2)

        # finalize game
        game.played = "closed"
        game.save()
        self.redis_state.set_game_state("is_running", False, game.id)

        # reset selection
        self.redis_state.set_selected_players([])
        self.redis_state.set_player_count(0)
        self._publish({"type":"player_list","player_list":[]}, target_client_id=None)
        # schedule next
        self.try_start_game()

    # ---- bingo checks for random players (keeps old logic but uses _publish) ----
    def check_bingo_for_random_players(self, calledNumbers, game):
        from game.models import Card
        from custom_auth.models import RandomPlayer

        selected_players = game.playerCard

        if game.winner != 0 or game.played == "closed":
            return

        called_numbers_list = calledNumbers + [0]
        game.total_calls = len(called_numbers_list)
        game.save_called_numbers(called_numbers_list)
        game.save()

        for entry in selected_players:
            if entry["user"] == 0:
                for card_id in entry["card"]:
                    try:
                        card = Card.objects.get(id=card_id)
                    except Card.DoesNotExist:
                        continue
                    numbers = json.loads(card.numbers)
                    winning_numbers = self.has_bingo(numbers, called_numbers_list)
                    if winning_numbers:
                        random_ids = [217, 72, 173, 1, 170]
                        rp = RandomPlayer.objects.filter(stake=Decimal(self.stake)).first()
                        if not rp:
                            continue
                        random_name = random.choice(rp.names) if rp.names else "Random"
                        random_id = random.choice(random_ids)
                        bones_amount = 0
                        stake = int(self.stake)
                        if stake in (10,20,50) and game.numberofplayers >= 10:
                            bones = len(called_numbers_list)
                            # multiplier logic same as before
                            if bones <= 5:
                                multiplier = 10
                            elif bones == 6:
                                multiplier = 9
                            elif bones == 7:
                                multiplier = 8
                            elif bones == 8:
                                multiplier = 7
                            elif bones == 9:
                                multiplier = 6
                            elif bones == 10:
                                multiplier = 5
                            elif bones == 11:
                                multiplier = 4
                            elif bones == 12:
                                multiplier = 3
                            elif bones == 13:
                                multiplier = 3
                            elif bones == 14:
                                multiplier = 2
                            elif bones == 15:
                                multiplier = 2
                            else:
                                multiplier = 0
                            bones_amount = stake * multiplier

                        game.winner = random_id
                        game.winner_card = card.id
                        game.winner_name = random_name
                        game.played = "closed"
                        game.total_calls = len(called_numbers_list)
                        game.save()

                        bingo_event = {
                            "type": "result",
                            "data": [{
                                "card_name": card.id,
                                "message": "Bingo",
                                "name": random_name,
                                "user_id": random_id,
                                "card": json.loads(card.numbers),
                                "winning_numbers": winning_numbers,
                                "called_numbers": called_numbers_list,
                                "bones_won": bones_amount
                            }],
                            "game_id": game.id
                        }

                        bingo_flag = self.redis_state.get_game_state("bingo", game.id)
                        if bingo_flag is False:
                            # credit random player
                            rp.wallet += (game.winner_price + bones_amount)
                            rp.save()
                            self.redis_state.set_game_state("bingo", True, game.id)
                            # broadcast bingo to all
                            self._publish(bingo_event, target_client_id=None)

                        return
    def check_bingo(self,payload):
        current_game_id = self.redis_state.get_stake_state("current_game_id")
        is_running = self.redis_state.get_game_state("is_running", current_game_id) if current_game_id else False
        user_id = payload.get("userId")

        if not is_running or not current_game_id:
            publish_event(
                stake=self.stake,
                event={"type": "error", "message": "No active game to check bingo."},
                target_client_id=self.client_id,
            )
            return

        called_numbers = self.redis_state.get_game_state("called_numbers", current_game_id) or []
        self.checkBingo(user_id, called_numbers, current_game_id)

    def checkBingo(self, user_id, called_numbers, game_id):
        import json
        from game.models import Card, Game
        from custom_auth.models import User

        result = []

        try:
            game = Game.objects.get(id=int(game_id))
        except Game.DoesNotExist:
            publish_event(
                stake=self.stake,
                event={"type": "error", "message": "Game not found"},
                target_client_id=self.client_id,
            )
            return

        # --- Get user's cards ---
        player_cards = [
            entry["card"]
            for entry in game.playerCard
            if int(entry["user"]) == int(user_id)
        ]

        if not player_cards:
            result.append({'user_id': user_id, 'message': 'Not a Player'})
            publish_event(
                stake=self.stake,
                event={"type": "result", "data": result, 'game_id': game.id},
                target_client_id=self.client_id,
            )
            return

        # --- Check if game already has a winner ---
        if game.played == "closed" or game.winner:
            return

        # --- Normalize called numbers (+ free space) ---
        called_numbers = list(set(called_numbers + [0]))
        game.total_calls = len(called_numbers)
        game.save_called_numbers(called_numbers)

        # --- Flatten cards ---
        def flatten(lst):
            for item in lst:
                if isinstance(item, list):
                    yield from flatten(item)
                else:
                    yield int(item)

        card_ids = list(flatten(player_cards))
        cards = Card.objects.filter(id__in=card_ids)

        user = User.objects.get(id=user_id)

        bingo_found = False

        for card in cards:
            numbers = json.loads(card.numbers)
            winning_numbers = self.has_bingo(numbers, called_numbers)

            if not winning_numbers:
                continue

            # --- Calculate bones if applicable ---
            bones_amount = 0
            stake = int(game.stake)
            if stake in (10, 20, 50) and game.numberofplayers >= 10:
                bones = len(called_numbers)
                multiplier_map = {
                    5: 10, 6: 9, 7: 8, 8: 7,
                    9: 6, 10: 5, 11: 4, 12: 3,
                    13: 3, 14: 2, 15: 2
                }
                bones_amount = stake * multiplier_map.get(bones, 0)

            # --- Update game winner fields ---
            game.winner = user.id
            game.winner_card = card.id
            game.winner_name = user.name
            game.played = "closed"
            game.total_calls = len(called_numbers)
            game.bonus = bones_amount

            # Save all winner fields explicitly
            game.save(update_fields=["winner", "winner_card", "winner_name", "played", "total_calls", "bonus"])

            # --- Pay user once ---
            if not self.redis_state.get_game_state("bingo", game.id):
                user.wallet += game.winner_price + bones_amount
                user.save()
                self.redis_state.set_game_state("bingo", True, game.id)

            result.append({
                "card_name": card.id,
                "message": "Bingo",
                "name": user.name,
                "user_id": user.id,
                "card": json.loads(card.numbers),
                "winning_numbers": winning_numbers,
                "called_numbers": called_numbers,
                "bones_won": bones_amount
            })

            bingo_found = True
            break  # stop checking after first winning card

        # --- Broadcast result ---
        publish_event(
            stake=self.stake,
            event={
                "type": "result",
                "data": result,
                "game_id": game.id
            },
            target_client_id=None if bingo_found else self.client_id
        )

        if not bingo_found:
            # No bingo for this user
            publish_event(
                stake=self.stake,
                event={
                    "type": "result",
                    "data": [{'user_id': user_id, 'message': 'No Bingo'}],
                    "game_id": game.id
                },
                target_client_id=self.client_id
            )


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

    def get_card_data(self, payload):
        user_id = payload.get("userId")
        user_cards = []
        selected_players = self.redis_state.get_selected_players()

        # --- Find player's cards ---
        for player in selected_players:
            if player.get("user") == int(user_id):
                cards_field = player.get("card")
                if isinstance(cards_field, list):
                    # flatten nested lists
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

        # --- No cards for this user ---
        if not user_cards:
            publish_event(
                stake=self.stake,
                target_client_id=self.client_id,
                event={
                    "type": "no_cards",
                    "message": "No cards found for user."
                }
            )
            return

        # --- Fetch card objects ---
        cards = Card.objects.filter(id__in=user_cards)
        bingo_table_data = [
            {
                "id": card.id,
                "numbers": json.loads(card.numbers)
            }
            for card in cards
        ]

        # --- Send card data to specific user ---
        publish_event(
            stake=self.stake,
            target_client_id=self.client_id,
            event={
                "type": "card_data",
                "cards": bingo_table_data
            }
        )

        
    def get_stake_stat(self):
        current_game_id = self.redis_state.get_stake_state("current_game_id")
        is_running = self.redis_state.get_game_state("is_running", current_game_id) if current_game_id else False

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
                    "called_numbers": self.redis_state.get_game_state("called_numbers", current_game_id) or [],
                    'player_list': self.redis_state.get_selected_players(),
                }
            except Game.DoesNotExist:
                self.try_start_game()
                stats = {
                    "type": "game_stat",
                    "running": False,
                    "message": "No game is currently running.",
                    "number_of_players": self.redis_state.get_player_count(),
                    "remaining_seconds": self.redis_state.get_remaining_time(),
                    'player_list': self.redis_state.get_selected_players(),
                }
        else:
            self.try_start_game()
            stats = {
                "type": "game_stat",
                "running": False,
                "message": "No game is currently running.",
                "number_of_players": self.redis_state.get_player_count(),
                "remaining_seconds": self.redis_state.get_remaining_time(),
                'player_list': self.redis_state.get_selected_players(),
            }

            print (stats)

        return stats
    def start_game_with_random_numbers(self, game, selected_players):
        import json
        import uuid
        import time
        from decimal import Decimal
        from custom_auth.models import RandomPlayer, User

        # --- Redis client ---
        redis_client = getattr(self.redis_state, "redis_client", None)
        if redis_client is None:
            redis_client = getattr(self.redis_state, "redis", None)
        if redis_client is None:
            print("⚠️ Redis client not available — aborting start_game_with_random_numbers")
            return

        # --- Distributed lock ---
        lock_key = f"game:{game.id}:broadcast_lock"
        lock_ttl = 10  # lock expires every 10 seconds unless renewed
        lock_token = str(uuid.uuid4())

        try:
            acquired = redis_client.set(lock_key, lock_token, nx=True, ex=lock_ttl)
            if not acquired:
                print(f"🔒 Another worker already broadcasting for game {game.id}. Exiting.")
                return

            print(f"✅ Acquired broadcast lock for game {game.id} token={lock_token}")

            # mark running
            self.game_id = game.id
            self.redis_state.set_game_state("is_running", True, game.id)
            self.redis_state.set_game_state("bingo", False, game.id)

            game.played = "Playing"
            game.save()

            # random player
            random_player = RandomPlayer.objects.filter(stake=Decimal(self.stake)).first()

            # broadcast "playing"
            publish_event(
                stake=self.stake,
                event={
                    'type': 'playing',
                    'game_id': game.id,
                    'message': 'Game is now playing'
                }
            )

            # ------- Remove duplicates + charge money -------
            stake_amount = Decimal(game.stake)
            updated_player_cards = []
            unique_entries = {}

            for entry in selected_players:
                user_id = int(entry.get("user", 0))
                if user_id == 0:
                    unique_entries.setdefault("zero_users", []).append(entry)
                else:
                    unique_entries[user_id] = entry

            dedup_players = list(unique_entries.get("zero_users", [])) + [
                entry for k, entry in unique_entries.items() if k != "zero_users"
            ]

            for entry in dedup_players:
                try:
                    user_id = entry["user"]
                    cards = entry["card"]

                    # flatten cards if nested
                    flat_cards = (
                        [c for sub in cards for c in sub]
                        if cards and isinstance(cards[0], list)
                        else cards
                    )

                    total_ded = stake_amount * len(flat_cards)

                    if int(user_id) == 0:
                        if random_player:
                            random_player.wallet -= total_ded
                            random_player.save(update_fields=['wallet'])
                    else:
                        try:
                            user = User.objects.get(id=user_id)
                        except User.DoesNotExist:
                            continue

                        if (user.wallet + user.bonus) < total_ded:
                            self.remove_player(user_id)
                            continue

                        remaining = total_ded

                        if user.wallet >= remaining:
                            user.wallet -= remaining
                            remaining = Decimal('0')
                        else:
                            remaining -= user.wallet
                            user.wallet = Decimal('0')

                        if remaining > 0:
                            user.bonus -= remaining

                        try:
                            user.no_of_games_played = (user.no_of_games_played or 0) + 1
                        except:
                            pass

                        user.save()

                    entry["card"] = flat_cards
                    updated_player_cards.append(entry)

                except Exception as e:
                    print("Error processing entry:", e)
                    try:
                        self.remove_player(user_id)
                    except:
                        pass

            # update game model
            game.numberofplayers = sum(len(p["card"]) for p in updated_player_cards)
            game.playerCard = updated_player_cards

            winner_price = stake_amount * game.numberofplayers

            if winner_price >= 100:
                admin_cut = winner_price * Decimal('0.2')
                winner_price -= admin_cut
            elif 50 <= winner_price < 100:
                admin_cut = winner_price * Decimal('0.1')
                winner_price -= admin_cut
            else:
                admin_cut = Decimal('0')

            game.admin_cut = admin_cut
            game.winner_price = winner_price
            game.save()

            bonus_text = "10X" if int(self.stake or 0) in [10, 20, 50] and game.numberofplayers >= 10 else ""

            publish_event(
                stake=self.stake,
                event={
                    'type': 'game_stat',
                    'number_of_players': game.numberofplayers,
                    'stake': game.stake,
                    'winner_price': float(game.winner_price),
                    'bonus': bonus_text,
                    'game_id': game.id,
                    'is_running': True
                }
            )

            time.sleep(5)

            # ------------ MAIN NUMBER LOOP ------------
            random_numbers = json.loads(game.random_numbers)

            for num in random_numbers:

                # renew lock (HEARTBEAT)
                current = redis_client.get(lock_key)
                if current != lock_token:
                    print(f"❌ Lost lock for game {game.id}. Stopping loop.")
                    return

                redis_client.expire(lock_key, lock_ttl)

                # stop if bingo or stopped externally
                if not self.redis_state.get_game_state("is_running", game.id):
                    break

                if self.redis_state.get_game_state("bingo", game.id):
                    break

                last_sent = self.redis_state.get_game_state("last_sent_number", game.id)
                if last_sent == num:
                    continue

                publish_event(
                    stake=self.stake,
                    event={
                        'type': 'random_number',
                        'random_number': num,
                        'game_id': game.id
                    }
                )

                # save state
                called = self.redis_state.get_game_state("called_numbers", game.id) or []
                if not isinstance(called, list):
                    called = []
                called.append(num)

                self.redis_state.set_game_state("called_numbers", called, game.id)
                self.redis_state.set_game_state("last_sent_number", num, game.id)

                time.sleep(2)

                # check random players
                try:
                    self.check_bingo_for_random_players(called, game)
                except Exception as e:
                    print("check_bingo_for_random_players error:", e)

                time.sleep(2)

            # ------------ END GAME ------------
            self.redis_state.set_game_state("is_running", False, game.id)

            self.redis_state.set_selected_players([])
            self.redis_state.set_player_count(0)
            self.redis_state.broadcast_player_list()

            self.try_start_game()

        except Exception as e:
            print("🚨 start_game_with_random_numbers error:", e)

        finally:
            # safe unlock with Lua
            try:
                release_script = """
                if redis.call("GET", KEYS[1]) == ARGV[1] then
                    return redis.call("DEL", KEYS[1])
                else
                    return 0
                end
                """
                redis_client.eval(release_script, 1, lock_key, lock_token)
                print(f"🔓 Released lock {lock_key}")
            except Exception as e:
                print("⚠️ Failed releasing lock:", e)
