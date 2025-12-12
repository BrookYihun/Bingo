# django_redis_worker.py
# Requirements: pip install redis
# Usage: set DJANGO_SETTINGS_MODULE and run
import os
import django
import json
import redis
import time

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Bingo.settings")
django.setup()

from game.models import Game, Card
from game.ws_handlers import GameManager, RedisState

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
channel_layer = None  
room_group_name = "game_all"
stake = 10

def publish_event(stake, event, target_client_id=None):
    """
    Publish an event to Redis.
    If target_client_id is set, only that client should handle it.
    """
    ch = f"game:{stake}:events"
    payload = {
        "event": event,
        "target_client_id": target_client_id  # None means broadcast
    }
    r.publish(ch, json.dumps(payload))

def process_message(msg):
    """Process incoming Redis messages."""
    try:
        raw = msg.get("data")  # JSON string
        incoming = json.loads(raw)  # dict
    except Exception as e:
        print("Bad payload:", e, msg)
        return

    # Now extract information
    stake = incoming.get("stake")
    payload = incoming.get("payload", {})
    msg_type = payload.get("type")
    room_group_name = "game_" + str(stake)
    client_id = incoming.get("client_id")

    redis_state = RedisState(r, stake)
    manager = GameManager(redis_state, stake, channel_layer, room_group_name)

    redis_state = RedisState(r, stake)
    manager = GameManager(redis_state, stake, room_group_name,client_id)


    # --- Handle number selection ---
    if msg_type == "select_number":
        result = manager.add_player(payload=payload)
        if result:
            publish_event(stake, result)

    # --- Handle number removal ---
    elif msg_type == "remove_number":
        result = manager.remove_player(payload=payload)
        if result:
            publish_event(stake, result)

    # --- Handle bingo check ---
    elif msg_type == "bingo":
        result = manager.check_bingo(payload=payload)
        if result:
            publish_event(stake, result)

    # --- Handle fetching user cards ---
    elif msg_type == "card_data":
        result = manager.get_card_data( payload=payload)
        if result:
            publish_event(
            stake,
            result,
            target_client_id=client_id  # ✅ ONLY THIS USER
        )

    # --- Fetch stake stats ---
    elif msg_type == "get_stake_stat":
        result = manager.get_stake_stat()
        if result:
            publish_event(stake, result, target_client_id=client_id)

    # --- Block user ---
    elif msg_type == "block_user":
        user_id = payload.get("userId")
        if user_id:
            # Implement block logic in ws_handlers if needed
            publish_event(stake, {"type": "user_blocked", "message": f"User {user_id} has been blocked."})
        else:
            publish_event(stake, {"type": "error", "message": "User ID not provided"})

    # --- Fetch active games ---
    elif msg_type == "fetch_active_game":
        active_games = manager.get_all_active_games()
        publish_event(stake, {"type": "active_game_data", "data": active_games})
    
    elif msg_type == "request_game_start":
        result = manager.try_start_game()
        if result:
            publish_event(stake, result)

    # --- Unknown type ---
    else:
        publish_event(stake, {"type": "error", "message": f"Unknown message type: {msg_type}"})

def on_message(msg):
    """Redis pubsub callback."""
    if msg['type'] in ('message','pmessage'):
        process_message(msg)

def run():
    """Start Redis worker."""
    pubsub = r.pubsub()
    pubsub.psubscribe('game:*:incoming')  # pattern
    print("Worker subscribed to pattern game:*:incoming")
    for msg in pubsub.listen():
        # Only handle actual messages
        if msg['type'] not in ('message','pmessage'):
            continue
        process_message(msg)

if __name__ == "__main__":
    run()
