# db_worker.py
import os, django, json, redis

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Bingo.settings")
django.setup()

from game.models import Game
from custom_auth.models import User

r = redis.Redis(decode_responses=True)

def handle_db_event(event):
    from game.models import Game
    from custom_auth.models import User, RandomPlayer
    from decimal import Decimal
    from django.db import transaction

    event_type = event.get("event")
    data = event.get("data", {})

    if event_type == "GAME_ENDED":
        game_id = data["game_id"]

        print("🧠 Processing GAME_ENDED for game:", game_id)

        try:
            with transaction.atomic():
                game = Game.objects.select_for_update().get(id=game_id)

                # ✅ Idempotency guard
                if game.played == "closed":
                    print("⚠️ Game already closed, skipping.")
                    return

                game.winner = data["winner_id"]
                game.winner_card = data["winner_card"]
                game.winner_name = data["winner_name"]
                game.winner_price = Decimal(str(data["winner_price"]))
                game.played = "closed"
                game.total_calls = data["total_calls"]
                game.save()

                # ✅ Wallet credit
                if int(data["winner_id"]) == 0:
                    rp = RandomPlayer.objects.get(stake=Decimal(game.stake))
                    rp.wallet += Decimal(str(data["winner_price"])) + Decimal(str(data["bones_won"]))
                    rp.save(update_fields=["wallet"])
                else:
                    user = User.objects.select_for_update().get(id=data["winner_id"])
                    user.wallet += Decimal(str(data["winner_price"])) + Decimal(str(data["bones_won"]))
                    user.save(update_fields=["wallet"])

                print("✅ GAME_END persisted successfully")

        except Exception as e:
            print("❌ Failed to persist GAME_ENDED:", e)
    

def run():
    pubsub = r.pubsub()
    pubsub.psubscribe("game:*:db_events")

    print("✅ DB Worker running")

    for msg in pubsub.listen():
        print("Received message:", msg)
        if msg["type"] != "pmessage":
            continue
        event = json.loads(msg["data"])
        handle_db_event(event)

if __name__ == "__main__":
    run()
