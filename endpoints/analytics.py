# FastAPI & SlowAPI imports
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from slowapi import Limiter
from slowapi.util import get_remote_address


# db imports
from database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, case, label, and_

# core imports
from core.schemas import ModelRegistrationRequest
from core.models import Model, Elo, Game, PlayerGame, PlayerLog

# import configs
from config import RATE_LIMIT, ENV_NAME_TO_ID, DEFAULT_ENV_ID, MIN_GAMES_LEADERBOARD

# import utilities
import secrets, time
from urllib.parse import unquote

# local imports
from utils import (
    categorize_reason,
    get_model, get_latest_elo,
    get_elo_history, get_recent_games,
    get_game_stats, 
    get_recent_games_details
)



router = APIRouter()
limiter = Limiter(key_func=get_remote_address)



@router.get("/models/{model_name}")
async def get_model_details(model_name: str, db: Session = Depends(get_db)):
    # 1) Decode
    model_name = unquote(model_name)
    # 2) Fetch model & description (raises 404 if not found)
    model = get_model(db, model_name)

    # 3) Gather data
    latest_elo = get_latest_elo(db, model_name, DEFAULT_ENV_ID)
    elo_history = get_elo_history(db, model_name, DEFAULT_ENV_ID)
    game_specific_stats, overall_stats = get_game_stats(db, model_name, DEFAULT_ENV_ID)
    recent_games = get_recent_games(db, model_name, DEFAULT_ENV_ID)
    # Get detailed game history (with environment, opponent and outcome)
    recent_game_history = get_recent_games_details(db, model_name, DEFAULT_ENV_ID, limit=10)

    # 4) Build response
    return {
        "model_name": model_name,
        "description": model.description or "",
        "elo": round(latest_elo.elo) if latest_elo else 1000,
        "wins": overall_stats["wins"],
        "losses": overall_stats["losses"],
        "draws": overall_stats["draws"],
        "total_games": overall_stats["total_games"],
        "win_rate": overall_stats["win_rate"],
        "avg_move_time": overall_stats["avg_move_time"],
        "elo_history": elo_history,
        "recent_games": recent_games,
        "recent_game_history": recent_game_history,
        "reason_counts": overall_stats["reason_counts"],
        "game_specific_stats": game_specific_stats,
    }




@router.get("/leaderboard")
def get_leaderboard(limit: int = Query(10), page: int = Query(1), db: Session = Depends(get_db)):

    def get_avg_move_time(model_name, specific_env_id=None):
        """Calculate average move time from observation to action for a model."""
        base_query = (
            db.query(func.avg(PlayerLog.timestamp_action - PlayerLog.timestamp_observation).label('avg_time'))
            .join(PlayerGame, PlayerLog.player_game_id == PlayerGame.id)
            .join(Game, PlayerGame.game_id == Game.id)
            .filter(
                PlayerLog.model_name == model_name,
                Game.environment_id == DEFAULT_ENV_ID,
                PlayerLog.timestamp_action.isnot(None),
                PlayerLog.timestamp_observation.isnot(None)
            )
        )

        # Add specific environment filter if provided
        if specific_env_id is not None:
            base_query = base_query.filter(Game.specific_env_id == specific_env_id)
            
        result = base_query.scalar()
        if result is None:
            return None
            
        return round(result, 2)

    # 1. Get the latest ELO timestamp for each model
    latest_elo_times = (
        db.query(
            Elo.model_name,
            func.max(Elo.updated_at).label('latest_time')
        )
        .filter(Elo.environment_id == DEFAULT_ENV_ID)
        .group_by(Elo.model_name)
        .subquery()
    )

    # 2. Get the latest ELO values for each model
    latest_elos = (
        db.query(
            Elo.model_name,
            Elo.elo
        )
        .join(
            latest_elo_times,
            and_(
                Elo.model_name == latest_elo_times.c.model_name,
                Elo.updated_at == latest_elo_times.c.latest_time
            )
        )
        .filter(Elo.environment_id == DEFAULT_ENV_ID)
        .subquery()
    )

    # 3. Get overall stats for each model
    model_stats = (
        db.query(
            PlayerGame.model_name,
            func.sum(case((PlayerGame.outcome == 'Win', 1), else_=0)).label('wins'),
            func.sum(case((PlayerGame.outcome == 'Loss', 1), else_=0)).label('losses'),
            func.sum(case((PlayerGame.outcome == 'Draw', 1), else_=0)).label('draws')
        )
        .join(Game, PlayerGame.game_id == Game.id)
        .filter(
            Game.environment_id == DEFAULT_ENV_ID,
            Game.status == 'finished'
        )
        .group_by(PlayerGame.model_name)
        .subquery()
    )

    # 4. Create a subquery to count the number of games per model.
    game_counts = (
        db.query(
            PlayerGame.model_name,
            func.count(PlayerGame.id).label("game_count")
        )
        .group_by(PlayerGame.model_name)
        .subquery()
    )

    # 5. Create a subquery of eligible models that meet the MIN_GAMES_LEADERBOARD criteria.
    eligible_models = (
        db.query(game_counts.c.model_name)
        .filter(game_counts.c.game_count >= MIN_GAMES_LEADERBOARD)
        .subquery()
    )

    # 6. Now join with the latest_elos and model_stats tables, restricting to eligible models.
    combined_query = (
        db.query(
            latest_elos.c.model_name,
            latest_elos.c.elo,
            model_stats.c.wins,
            model_stats.c.losses,
            model_stats.c.draws,
            game_counts.c.game_count
        )
        .join(model_stats, latest_elos.c.model_name == model_stats.c.model_name)
        .join(game_counts, latest_elos.c.model_name == game_counts.c.model_name)
        .filter(latest_elos.c.model_name.in_(db.query(eligible_models.c.model_name)))
        .order_by(desc(latest_elos.c.elo))
    )

    # Apply pagination on the final query.
    combined_data = combined_query.offset((page - 1) * limit).limit(limit).all()

    def get_game_specific_stats(model_name):
        # Initialize for all possible game IDs (0-9 as strings)
        stats_dict = {
            str(i): {
                'wins': 0,
                'losses': 0,
                'draws': 0,
                'total_games': 0,
                'avg_move_time': get_avg_move_time(model_name, str(i))
            }
            for i in range(10)
        }
        
        results = (
            db.query(
                Game.specific_env_id,
                func.count(PlayerGame.id).label('total_games'),
                func.sum(case((PlayerGame.outcome == 'Win', 1), else_=0)).label('wins'),
                func.sum(case((PlayerGame.outcome == 'Loss', 1), else_=0)).label('losses'),
                func.sum(case((PlayerGame.outcome == 'Draw', 1), else_=0)).label('draws')
            )
            .join(PlayerGame, Game.id == PlayerGame.game_id)
            .filter(
                Game.environment_id == DEFAULT_ENV_ID,
                Game.status == 'finished',
                PlayerGame.model_name == model_name,
                Game.specific_env_id.isnot(None)
            )
            .group_by(Game.specific_env_id)
            .all()
        )
        
        # Update stats_dict with results
        for stat in results:
            game_id = stat.specific_env_id
            if game_id in ENV_NAME_TO_ID:
                game_id = ENV_NAME_TO_ID[game_id]
            elif game_id.isdigit():
                game_id = str(game_id)
            else:
                continue  # Skip invalid game IDs

            if game_id in stats_dict:
                stats_dict[game_id].update({
                    'wins': stat.wins or 0,
                    'losses': stat.losses or 0,
                    'draws': stat.draws or 0,
                    'total_games': stat.total_games or 0
                })
        
        return stats_dict

    def get_elo_history(model_name):
        history = (
            db.query(Elo)
            .filter(
                Elo.model_name == model_name,
                Elo.environment_id == DEFAULT_ENV_ID
            )
            .order_by(Elo.updated_at)
            .all()
        )
        return [
            {
                "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(h.updated_at)),
                "elo": round(h.elo)
            }
            for h in history
        ]

    def get_recent_games(model_name):
        return (
            db.query(PlayerGame.outcome)
            .join(Game, PlayerGame.game_id == Game.id)
            .filter(
                PlayerGame.model_name == model_name,
                Game.status == 'finished',
                Game.environment_id == DEFAULT_ENV_ID
            )
            .order_by(desc(Game.started_at))
            .limit(10)
            .all()
        )

    leaderboard = []
    rank = (page - 1) * limit + 1

    for row in combined_data:
        model_name = row.model_name

        game_stats = get_game_specific_stats(model_name)
        overall_avg_time = get_avg_move_time(model_name)
        recent_games = get_recent_games(model_name)
        elo_history = get_elo_history(model_name)

        total_games = (row.wins or 0) + (row.losses or 0) + (row.draws or 0)
        win_rate = f"{((row.wins or 0)/total_games * 100 if total_games > 0 else 0):.1f}%"

        leaderboard.append({
            "rank": rank,
            "model_name": model_name,
            "wins": row.wins or 0,
            "losses": row.losses or 0,
            "draws": row.draws or 0,
            "win_rate": win_rate,
            "elo": round(row.elo),
            "recent_games": [game.outcome for game in recent_games],
            "elo_history": elo_history,
            "game_specific_stats": game_stats,
            "total_games": total_games,
            "avg_move_time": overall_avg_time
        })
        rank += 1

    return {
        "leaderboard": leaderboard,
        "page": page,
        "limit": limit,
        # Optionally add total pages/next_page/prev_page info if available.
    }