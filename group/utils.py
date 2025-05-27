from django.utils import timezone
from group.models import Group, GroupGame
from game.models import Game

def create_recurring_group_games():
    now = timezone.now()
    recurring_groups = Group.objects.filter(is_recurring=True)

    for group in recurring_groups:
        last_group_game = group.games.order_by('-start_time').first()

        should_create = False

        if not last_group_game:
            should_create = True
        else:
            last_game = last_group_game.game
            # Condition 1: game status is 'Started'
            if last_game.played == 'Started' or last_game.played == 'Playing' or last_game.played == 'closed':
                should_create = True
            # Condition 2: enough time has passed since last game
            elif group.recurrence_interval_seconds:
                next_time = last_group_game.start_time + timezone.timedelta(seconds=group.recurrence_interval_seconds)
                should_create = now >= next_time

        if should_create:
            new_game = Game.objects.create(
                stake=str(group.stake),
                numberofplayers=0,
                played="Created"
            )

            GroupGame.objects.create(
                group=group,
                game=new_game,
                start_time=now
            )

            print(f"Created new recurring game for group '{group.name}' at {now}")
