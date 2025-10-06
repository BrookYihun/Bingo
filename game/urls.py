from django.urls import path
from .views import get_active_games, get_user_profile, start_game, get_game_stat, get_bingo_card, \
    get_playing_bingo_card, get_user_game_history, get_total_games_played, get_total_wins, \
    get_recent_games, get_game_participants, get_global_leaderboard, withdraw, transfer, transaction_history, \
    transfer_history, get_online_agent_payment_methods, get_deposit_accounts, auto_deposit, get_user_stats, \
    get_total_withdrawal, get_total_deposit

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
 path('user/total-deposit/', get_total_deposit, name='total-deposit'),
    path('user/total-withdrawal/', get_total_withdrawal, name='total-withdrawal'),
    path('user/stats/', get_user_stats, name='user-stats'),
    # urls.py
    path('api/auto-deposit/', auto_deposit, name='auto_deposit'),
    path('api/deposit-accounts/', get_deposit_accounts, name='deposit_accounts'),
    path('api/online-agent-payment-methods/', get_online_agent_payment_methods,
         name='online_agent_payment_methods'),
    path('api/withdraw/', withdraw, name='withdraw'),
    path('api/transfer/', transfer, name='transfer'),
path('api/transaction-history/',  transaction_history, name='transaction_history'),
path('api/transfer-history/',  transfer_history, name='transfer_history'),
]
