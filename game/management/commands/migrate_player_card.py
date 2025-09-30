import json

from django.core.management import BaseCommand
from django.db import transaction

from custom_auth.models import User
from game.models import Game, UserGameParticipation


class Command(BaseCommand):
    help="Migrate legacy playerCard data to UserGameParticipation "

    def handle(self, *args, **options):
        closed_games=Game.objects.filter(played='closed')
        self.stdout.write(f"Found {closed_games.count()} closed games to migrate...")

        migrated=0
        errors=0

        for game in closed_games:
            try:
                if not game.playerCard:
                    continue
                if isinstance(game.playerCard,str):
                    players=json.loads(game.playerCard)
                else:
                    players=game.playerCard

                if not isinstance(players,list):
                    self.stderr.write(f"Invalid playerCard format in game {game.id}: {game.playerCard}")
                    errors+=1
                    continue
                with transaction.atomic():
                    for entry in players:
                        if not isinstance(entry,dict):
                            continue
                        user_id=entry.get('user')
                        if not user_id:
                            continue
                        try:
                            user=User.objects.get(id=user_id)
                        except User.DoesNotExist:
                            self.stderr.write(f"User {user_id} not found for {game.id}")

                        participation, created=UserGameParticipation.objects.get_or_create(
                            user=user,
                            game=game,
                            defaults={'times_played':1}

                        )
                        if created:
                            migrated+=1
            except Exception as e:
                self.stderr.write(f"Error migrating game {game.id}: {e}")
                errors+=1
        self.stdout.write(
            self.style.SUCCESS(f"Migration completed: {migrated} participations created, {errors} errors.")

        )
