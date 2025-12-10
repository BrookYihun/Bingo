# twisted_ws_server.py
# Requirements:
#   pip install autobahn[twisted] redis
# Run: python twisted_ws_server.py
# Environment variables (optional):
#   REDIS_HOST, REDIS_PORT

from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet import reactor, endpoints
import redis
import os
import json
import urllib.parse
import threading
import time
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Bingo.settings")
django.setup()

from game.ws_handlers import RedisState

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

connected_clients = {}  # room_name -> set of WebSocket instances
ch = None
def extract_stake_from_path(path_bytes):
    try:
        path = path_bytes.decode() if isinstance(path_bytes, (bytes, bytearray)) else str(path_bytes)
        parts = path.split('?')[0].strip('/').split('/')
        
        # last part of /ws/game-socket/all/ is "all"
        if parts:
            return parts[-1]  # return last part even if not numeric
        return None
    except Exception:
        return None

class BingoWSProtocol(WebSocketServerProtocol):
    def onConnect(self, request):
        self.request = request
        self._redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        self.stake = extract_stake_from_path(request.path)
        if not self.stake:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(request.uri).query)
            self.stake = (qs.get('stake') or [None])[0]
        self.room_name = f"game_{self.stake}" if self.stake else "game_unknown"
        self.client_id = f"{self.peer}-{id(self)}"
        self._stop_pubsub = threading.Event()

    def onOpen(self):
        # Start Redis Pub/Sub listener
        self.pubsub = self._redis.pubsub()
        channel = f"game:{self.stake}:events"
        self.pubsub.subscribe(channel)
        print(f"Subscribed to Redis channel: {channel}")
        threading.Thread(target=self.listen_to_redis, daemon=True).start()
        redis_state = RedisState(self._redis, self.stake)

        # --- register this client into connected_clients ---
        clients = connected_clients.setdefault(self.room_name, set())
        clients.add(self)
        print(f"Client registered: {self.client_id} in {self.room_name} (total {len(clients)})")
        # ---------------------------------------------------

        # ... rest of onOpen (send initial state) ...


        # Send initial game state to client
        if self.stake == "all":
            all_games = redis_state.get_all_active_games()
            self.send_ws_message(json.dumps({
                "type": "active_game_data",
                "data": all_games
            }))
        else:
            current_game_id = redis_state.get_stake_state("current_game_id")
            is_running = redis_state.get_game_state("is_running", current_game_id) if current_game_id else False

            if is_running and current_game_id:
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
                        "number_of_players": current_game.numberofplayers,
                        "stake": current_game.stake,
                        "winner_price": float(current_game.winner_price),
                        "bonus": bonus_text,
                        "game_id": current_game.id,
                        "running": True,
                        "called_numbers": redis_state.get_game_state("called_numbers", current_game_id) or [],
                    }

                    # Notify about current game in progress
                    self.send_ws_message(json.dumps({
                        "type": "game_in_progress",
                        "game_id": current_game_id
                    }))
                except Game.DoesNotExist:
                    ch = f"game:{self.stake}:incoming"
                    self._redis.publish(ch, json.dumps({
                        "client_id": self.client_id,
                        "remote": str(self.peer),
                        "room_name": self.room_name,
                        "stake": self.stake,
                        "payload": {"type": "request_game_start"}}))
                    stats = {
                        "type": "game_stat",
                        "running": False,
                        "message": "No game is currently running.",
                        "number_of_players": redis_state.get_player_count(),
                        "remaining_seconds": redis_state.get_remaining_time(),
                    }
            else:
                self._redis.publish(ch, json.dumps({
                        "client_id": self.client_id,
                        "remote": str(self.peer),
                        "room_name": self.room_name,
                        "stake": self.stake,
                        "payload": {"type": "request_game_start"}}))
                stats = {
                    "type": "game_stat",
                    "running": False,
                    "message": "No game is currently running.",
                    "number_of_players": redis_state.get_player_count(),
                    "remaining_seconds": redis_state.get_remaining_time(),
                }

            # Send initial stats
            self.send_ws_message(json.dumps(stats))
            # Send current selected player list
            self.send_ws_message(json.dumps({
                "type": "player_list",
                "player_list": redis_state.get_selected_players()
            }))


    def listen_to_redis(self):
        try:
            for message in self.pubsub.listen():
                if self._stop_pubsub.is_set():
                    break
                if message['type'] == 'message':
                    data = message['data']
                    # Broadcast to all clients in the room
                    reactor.callFromThread(self.broadcast_ws_message, data)
        except Exception as e:
            print("Error in Redis pubsub listener:", e)

    def broadcast_ws_message(self, msg):
        """
        msg is a JSON string with keys:
          - event: dict (the payload to send to client(s))
          - target_client_id: optional (only this client_id receives it)
        """
        try:
            payload = json.loads(msg)
            event = payload.get("event", payload)  # if payload already is event dict
            target_client_id = payload.get("target_client_id")
            room_name = payload.get("room_name")  # optional: explicit room
        except Exception:
            # fallback: try to send raw string to this connection's room
            event = msg
            target_client_id = None
            room_name = None

        # prefer explicit room_name in message, else use this connection's room_name
        room = room_name or self.room_name

        clients = list(connected_clients.get(room, set()))
        if not clients:
            # no registered clients in that room
            return

        # send to matching clients; iterate snapshot to avoid mutation issues
        for client in clients:
            try:
                if target_client_id and client.client_id != target_client_id:
                    continue
                # ensure we send JSON string
                if isinstance(event, (dict, list)):
                    client.send_ws_message(json.dumps(event))
                else:
                    client.send_ws_message(str(event))
            except Exception as e:
                print(f"Error sending to client {getattr(client,'client_id',None)}: {e}")


    def send_ws_message(self, msg):
        if self.transport and not self.transport.disconnecting:
            self.sendMessage(msg.encode('utf-8'), isBinary=False)

    def connectionLost(self, reason):
        if hasattr(self, "_stop_pubsub"):
            self._stop_pubsub.set()

        if hasattr(self, "pubsub"):
            try:
                self.pubsub.close()
            except Exception:
                pass

        try:
            clients = connected_clients.get(self.room_name)
            if clients and self in clients:
                clients.remove(self)
                if not clients:
                    connected_clients.pop(self.room_name, None)
                print(f"Client unregistered: {self.client_id} from {self.room_name}")
        except Exception as e:
            print("Error unregistering client:", e)

        super().connectionLost(reason)

    def onMessage(self, payload, isBinary):
        if isBinary:
            return
        try:
            text = payload.decode('utf-8')
            data = json.loads(text)
            print(data)
        except Exception:
            self.send_ws_message(json.dumps({"type": "error", "message": "invalid_json"}))
            return

        outgoing = {
            "client_id": self.client_id,
            "remote": str(self.peer),
            "room_name": self.room_name,
            "stake": self.stake,
            "payload": data
        }

        try:
            ch = f"game:{self.stake}:incoming"
            self._redis.publish(ch, json.dumps(outgoing))
        except Exception as e:
            print("Failed to publish to Redis incoming:", e)
            self.send_ws_message(json.dumps({"type": "error", "message": "publish_failed"}))


if __name__ == "__main__":
    factory = WebSocketServerFactory(u"ws://0.0.0.0:9000")
    factory.protocol = BingoWSProtocol
    endpoint = endpoints.TCP4ServerEndpoint(reactor, 9000)
    endpoint.listen(factory)
    print("Twisted WebSocket server listening on 0.0.0.0:9000")
    reactor.run()
