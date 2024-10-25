from django.urls import path
from .views import get_active_games, start_game

urlpatterns = [
    path('api/get-game-data/', get_active_games, name='get_active_games'),
    path('api/start-game/<str:stake>/', start_game, name='start_game'),
]
