from src.gamification.routes.gamification import router as gamification_router
from src.gamification.routes.leaderboard import router as leaderboard_router
from src.gamification.routes.daily_questions import router as daily_questions_router

__all__ = ["gamification_router", "leaderboard_router", "daily_questions_router"]
