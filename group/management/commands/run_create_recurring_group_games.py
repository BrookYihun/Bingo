from django.core.management.base import BaseCommand
from group.utils import create_recurring_group_games

class Command(BaseCommand):
    help = 'Creates games for recurring groups'

    def handle(self, *args, **kwargs):
        create_recurring_group_games()
        self.stdout.write("Checked and created recurring games if needed.")
