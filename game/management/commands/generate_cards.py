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

        # Create a list to store the formatted bingo card strings for the file
        card_strings = []

        # Store the unique cards in the database
        for num, card_json in enumerate(used_cards, start=1):
            # Create a new Card instance for each unique card
            bingo_card_model = Card(id=num, numbers=card_json)
            bingo_card_model.save()

            # Convert the JSON string back to a list for formatting
            bingo_card = json.loads(card_json)

            # Format the card as a 5x5 table with the ID
            card_str = f"Card ID: {num}\n"
            for row in bingo_card:
                card_str += " ".join(f"{num:2}" for num in row) + "\n"
            card_str += "\n"  # Add a blank line between cards
            card_strings.append(card_str)

        # Write the cards to a num.txt file
        with open("num.txt", "w") as file:
            file.writelines(card_strings)

        self.stdout.write(self.style.SUCCESS('Successfully generated and stored 500 unique bingo cards.'))
        self.stdout.write(self.style.SUCCESS('Bingo cards have been saved to num.txt.'))
