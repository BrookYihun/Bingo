from django.db import models
import json

class Card(models.Model):
    numbers = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"Bingo Card {self.id}"
    
class Game(models.Model):
    stake = models.CharField(default='20',max_length=50)
    numberofplayers = models.IntegerField(default=0)
    playerCard = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(auto_now_add=True)
    played = models.CharField(max_length=50,default='Created')
    total_calls = models.IntegerField(default=0)
    called_numbers = models.JSONField(default=dict)
    random_numbers = models.JSONField(default=dict)
    winner_price = models.DecimalField(max_digits=100,default=0,decimal_places=2)
    admin_cut = models.DecimalField(max_digits=100,default=0,decimal_places=2)
    bonus = models.IntegerField(default=0)

    def __str__(self) -> str:
        return f"Game number {self.id}"
    
    def save_random_numbers(self, numbers):
        self.random_numbers = json.dumps(numbers)
        self.save()
    
    def save_called_numbers(self, numbers):
        self.called_numbers = json.dumps(numbers)
        self.save()