from django.core.management.base import BaseCommand
from game.models import Game
from game.utils import generate_random_numbers  # Ensure this function exists
from django.utils.timezone import now
import time

class Command(BaseCommand):
    help = "Continuously monitor and maintain active games for each stake"

    def handle(self, *args, **kwargs):
        stakes = [10, 20, 50, 100]  # List of stakes to monitor
        
        self.stdout.write("Starting game maintenance...")

        while True:
            for stake in stakes:
                # Fetch active games for the stake
                active_games = Game.objects.filter(
                    stake=str(stake),
                    played__in=['Started', 'Playing']
                ).order_by('-created_at')

                # Ensure at least two active games
                if active_games.count() < 2:
                    self.stdout.write(f"Adding games for stake {stake}")
                    while active_games.count() < 2:
                        Game.objects.create(
                            stake=str(stake),
                            numberofplayers=0,
                            played='Started',
                            random_numbers=generate_random_numbers(),
                            called_numbers={},
                            created_at=now(),
                            started_at=now(),
                        )
                        active_games = Game.objects.filter(
                            stake=str(stake),
                            played__in=['Started', 'Playing']
                        ).order_by('-created_at')

            # Sleep for a while to avoid overloading the database
            time.sleep(10)  # Check every 10 seconds
