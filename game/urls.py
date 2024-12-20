from django.urls import path
from .views import get_active_games, get_user_profile, start_game,get_game_stat,get_bingo_card,get_playing_bingo_card

urlpatterns = [
    path('api/get-game-data/', get_active_games, name='get_active_games'),
    path('api/start-game/<str:stake>/', start_game, name='start_game'),
    path('api/get-bingo-card/', get_bingo_card, name='get_bingo_card'),
    path('api/get-playing-bingo-card/', get_playing_bingo_card, name='get_playing_bingo_card'),
    path('api/get-game-stats/<int:game_id>/<int:user_id>/', get_game_stat, name='get_game_stat'),
    path('api/get-profile/<int:user_id>/',get_user_profile,name="get_profile")
]
