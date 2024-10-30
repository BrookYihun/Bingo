import random
from django.core.management.base import BaseCommand
from game.models import Card
import json

def generate_bingo_card():
    bingo_card = []
    used_numbers = set()

    for i in range(5):
        row = []
        for j in range(5):
            if i == 2 and j == 2:  # Center space in a Bingo card is usually free
                row.append(0)
            else:
                lower_bound = j * 15 + 1
                upper_bound = (j + 1) * 15
                num = random.randint(lower_bound, upper_bound)
                while num in used_numbers:
                    num = random.randint(lower_bound, upper_bound)
                used_numbers.add(num)
                row.append(num)
        bingo_card.append(row)
    return bingo_card

class Command(BaseCommand):
    def handle(self, *args, **options):
        used_cards = set()
        total_cards = 500

        # Generate unique bingo cards
        while len(used_cards) < total_cards:
            bingo_card = generate_bingo_card()
            card_json = json.dumps(bingo_card)
            used_cards.add(card_json)

        # Store the unique cards in the database
        for num, card_json in enumerate(used_cards, start=1):
            # Create a new Card instance for each unique card
            bingo_card_model = Card(id=num, numbers=card_json)
            bingo_card_model.save()

        self.stdout.write(self.style.SUCCESS('Successfully generated and stored 500 unique bingo cards.'))
