import random
import json
from django.core.management.base import BaseCommand
from game.models import Card


def generate_bingo_card():
    bingo_card = []
    used_numbers = set()

    for i in range(5):
        row = []
        for j in range(5):
            if i == 2 and j == 2:  # Center space is free
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
    help = "Regenerate and update bingo cards for existing IDs"

    def handle(self, *args, **options):
        total_cards = 500
        used_cards = set()

        # Generate 500 unique cards
        while len(used_cards) < total_cards:
            bingo_card = generate_bingo_card()
            card_json = json.dumps(bingo_card)
            used_cards.add(card_json)

        # Update existing 500 cards
        for card_obj, card_json in zip(Card.objects.order_by("id")[:total_cards], used_cards):
            card_obj.numbers = card_json
            card_obj.save(update_fields=["numbers"])

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {total_cards} bingo cards."))
