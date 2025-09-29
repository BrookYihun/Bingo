from django.urls import path
from .views import get_active_games, get_user_profile, start_game, get_game_stat, get_bingo_card, \
    get_playing_bingo_card, get_user_game_history, get_total_games_played, get_total_wins, \
    get_recent_games, get_game_participants, get_global_leaderboard

urlpatterns = [
    path('api/get-game-data/', get_active_games, name='get_active_games'),
    path('api/start-game/<str:stake>/', start_game, name='start_game'),
    path('api/get-bingo-card/', get_bingo_card, name='get_bingo_card'),
    path('api/get-playing-bingo-card/', get_playing_bingo_card, name='get_playing_bingo_card'),
    path('api/get-game-stats/<int:game_id>/', get_game_stat, name='get_game_stat'),
    path('api/get-profile/',get_user_profile,name="get_profile"),
    path('history/', get_user_game_history, name='game-history'),
    path('leaderboard/', get_global_leaderboard, name='global-leaderboard'),
    path('game/<int:game_id>/participants/', get_game_participants, name='game-participants'),
path('recent/', get_recent_games, name='recent-games'),
    path('wins/', get_total_wins, name='user-wins'),
    path('games-played/', get_total_games_played, name='user-games-played'),

]
