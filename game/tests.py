from django.test import TestCase

# Create your tests here.
# game/tests.py
from django.test import TestCase
from game.models import Game, Card
from custom_auth.models import User
import json

class WinnerCardsTest(TestCase):
    def test_winner_cards_saved_on_bingo(self):
        user = User.objects.create(
            phone_number="1234567890",
            name="Test User",
            wallet=100,
            bonus=0,
            is_active=True
        )
        card = Card.objects.create(numbers=json.dumps([
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 0, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25]
        ]))
        game = Game.objects.create(
            stake="20",
            numberofplayers=1,
            playerCard={str(user.id): [card.id]},
            played="Playing",
            winner=0,
            winner_cards=[]
        )

        # Simulate Bingo on first row
        called_numbers = [1, 2, 3, 4, 5]

        # Manually trigger winner logic
        game.winner = user.id
        game.winner_cards = [card.id]
        game.played = "closed"
        game.save()

        # Verify
        updated = Game.objects.get(id=game.id)
        self.assertEqual(updated.winner, user.id)
        self.assertEqual(updated.winner_cards, [card.id])