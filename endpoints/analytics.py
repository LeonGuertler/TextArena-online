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





# @router.get("/models/{model_name}")
# async def get_model_details(model_name: str, db: Session = Depends(get_db)):
#     ENV_ID = "BalancedSubset-v0"

#     model_name = unquote(model_name)
    
#     # Get basic model info
#     model = db.query(Model).filter(Model.model_name == model_name).first()
#     if not model:
#         raise HTTPException(status_code=404, detail="Model not found")

#     # Get latest ELO
#     latest_elo = (
#         db.query(Elo)
#         .filter(Elo.model_name == model_name, Elo.environment_id == ENV_ID)
#         .order_by(desc(Elo.updated_at))
#         .first()
#     )

#     # Get ELO history
#     elo_history = (
#         db.query(Elo)
#         .filter(Elo.model_name == model_name, Elo.environment_id == ENV_ID)
#         .order_by(Elo.updated_at)
#         .all()
#     )
    
#     elo_history = [
#         {
#             "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(h.updated_at)),
#             "elo": round(h.elo)
#         }
#         for h in elo_history
#     ]

#     # Get overall stats
#     overall_stats = (
#         db.query(
#             func.count(PlayerGame.id).label("total_games"),
#             func.sum(case((PlayerGame.outcome == "Win", 1), else_=0)).label("wins"),
#             func.sum(case((PlayerGame.outcome == "Loss", 1), else_=0)).label("losses"),
#             func.sum(case((PlayerGame.outcome == "Draw", 1), else_=0)).label("draws"),
#             func.avg(
#                 case(
#                     # Only compute average on logs where we have both timestamps
#                     (PlayerLog.timestamp_action.isnot(None) & PlayerLog.timestamp_observation.isnot(None),
#                      PlayerLog.timestamp_action - PlayerLog.timestamp_observation),
#                     else_=None,
#                 )
#             ).label("avg_move_time"),
#         )
#         .join(Game, Game.id == PlayerGame.game_id)
#         .outerjoin(PlayerLog, PlayerLog.player_game_id == PlayerGame.id)
#         .filter(
#             PlayerGame.model_name == model_name,
#             Game.status == "finished",
#         )
#         .first()
#     )

#     # These might be None if there are no finished games at all
#     total_games = overall_stats.total_games or 0
#     wins = overall_stats.wins or 0
#     losses = overall_stats.losses or 0
#     draws = overall_stats.draws or 0
#     avg_move_time = overall_stats.avg_move_time  # Could be None
#     if avg_move_time is not None:
#         avg_move_time = round(avg_move_time, 2)

#     print(overall_stats)

#     # Get game-specific stats with the environment name as is
#     game_stats = (
#         db.query(
#             Game.specific_env_id,
#             func.count(PlayerGame.id).label('total_games'),
#             func.sum(case((PlayerGame.outcome == 'Win', 1), else_=0)).label('wins'),
#             func.sum(case((PlayerGame.outcome == 'Loss', 1), else_=0)).label('losses'),
#             func.sum(case((PlayerGame.outcome == 'Draw', 1), else_=0)).label('draws'),
#             func.avg(PlayerLog.timestamp_action - PlayerLog.timestamp_observation).label('avg_move_time')
#         )
#         .join(PlayerGame, Game.id == PlayerGame.game_id)
#         .outerjoin(PlayerLog, PlayerLog.player_game_id == PlayerGame.id)
#         .filter(
#             PlayerGame.model_name == model_name,
#             Game.environment_id == ENV_ID,
#             Game.status == 'finished',
#             Game.specific_env_id.isnot(None)
#         )
#         .group_by(Game.specific_env_id)
#         .all()
#     )

#     # Initialize stats dict with numeric IDs
#     game_specific_stats = {
#         str(i): {
#             'wins': 0,
#             'losses': 0,
#             'draws': 0,
#             'total_games': 0,
#             'avg_move_time': None
#         }
#         for i in range(9)  # 0-8 environments
#     }

#     # Print debug information
#     print(f"Found {len(game_stats)} game stats entries")
    
#     # Update with actual stats
#     for stat in game_stats:
#         # Print each stat for debugging
#         print(f"Processing stat: {stat.specific_env_id}, games: {stat.total_games}")
        
#         # Convert environment name to ID if needed
#         env_name = stat.specific_env_id
#         game_id = ENV_NAME_TO_ID.get(env_name, env_name)
        
#         # Print the mapping
#         print(f"Mapped {env_name} to {game_id}")
        
#         if game_id in game_specific_stats:
#             game_specific_stats[game_id].update({
#                 'wins': stat.wins or 0,
#                 'losses': stat.losses or 0,
#                 'draws': stat.draws or 0,
#                 'total_games': stat.total_games or 0,
#                 'avg_move_time': round(stat.avg_move_time, 2) if stat.avg_move_time is not None else None
#             })
#         else:
#             print(f"Warning: game_id {game_id} not found in game_specific_stats")

#     # Get recent games
#     recent_games = (
#         db.query(PlayerGame.outcome)
#         .join(Game)
#         .filter(
#             PlayerGame.model_name == model_name,
#             Game.status == 'finished',
#             Game.environment_id == ENV_ID
#         )
#         .order_by(desc(Game.started_at))
#         .limit(10)
#         .all()
#     )

#     total_games = overall_stats.total_games or 0
#     if total_games > 0:
#         win_rate = f"{((overall_stats.wins or 0) / total_games * 100):.1f}%"
#     else:
#         win_rate = "N/A"

#     # Print final stats for debugging
#     print(f"Final game_specific_stats: {game_specific_stats}")

#     # Make sure we only query this model’s finished games
#     finished_games = (
#         db.query(Game.reason, PlayerGame.outcome)
#         .join(PlayerGame, Game.id == PlayerGame.game_id)
#         .filter(
#             PlayerGame.model_name == model_name,
#             Game.status == "finished"
#         )
#         .all()
#     )
    
#     reason_counts = {
#         "invalid_move": {"total": 0, "win": 0, "loss": 0, "draw": 0},
#         "timeout": {"total": 0, "win": 0, "loss": 0, "draw": 0},
#         "game_logic": {"total": 0, "win": 0, "loss": 0, "draw": 0},
#     }

#     for (game_reason, outcome) in finished_games:
#         cat = categorize_reason(game_reason)  # as defined above

#         reason_counts[cat]["total"] += 1
        
#         if outcome == "Win":
#             reason_counts[cat]["win"] += 1
#         elif outcome == "Loss":
#             reason_counts[cat]["loss"] += 1
#         elif outcome == "Draw":
#             reason_counts[cat]["draw"] += 1
#         else:
#             # Some older records might have None or custom outcome
#             pass

#     return {
#         "model_name": model_name,
#         "elo": round(latest_elo.elo) if latest_elo else 1000,
#         "wins": overall_stats.wins or 0,
#         "losses": overall_stats.losses or 0,
#         "draws": overall_stats.draws or 0,
#         "total_games": total_games,
#         "win_rate": win_rate,
#         "avg_move_time": round(overall_stats.avg_move_time, 2) if overall_stats.avg_move_time is not None else None,
#         "elo_history": elo_history,
#         "recent_games": [game.outcome for game in recent_games],
#         "game_specific_stats": game_specific_stats,
#         "reason_counts": reason_counts,
#         "description": model.description
#     }




# @router.get("/models/{model_name}")
# async def get_model_details(model_name: str, db: Session = Depends(get_db)):
#     # 1) decode
#     model_name = unquote(model_name)
#     # 2) fetch model & description
#     model = get_model(db, model_name)  # raises 404 if not found

#     # 3) gather data
#     latest_elo = get_latest_elo(db, model_name, DEFAULT_ENV_ID)
#     elo_history = get_elo_history(db, model_name, DEFAULT_ENV_ID)
#     game_specific_stats, overall_stats = get_game_stats(db, model_name, DEFAULT_ENV_ID)
#     recent_games = get_recent_games(db, model_name, DEFAULT_ENV_ID)

#     # 4) Build response
#     return {
#         "model_name": model_name,
#         "description": model.description or "",  # add description to the response
#         "elo": round(latest_elo.elo) if latest_elo else 1000,
#         "wins": overall_stats["wins"],
#         "losses": overall_stats["losses"],
#         "draws": overall_stats["draws"],
#         "total_games": overall_stats["total_games"],
#         "win_rate": overall_stats["win_rate"],
#         "avg_move_time": overall_stats["avg_move_time"],
#         "elo_history": elo_history,
#         "recent_games": recent_games,
#         # For a simpler structure, you can either return reason_counts here,
#         # or let the front-end read them from the environment stats and overall stats:
#         "reason_counts": overall_stats["reason_counts"],  # Overall reason stats
#         "game_specific_stats": game_specific_stats,        # Per environment stats
#     }


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





# @router.get("/leaderboard")
# def get_leaderboard(limit: int = Query(10), page: int = Query(1), db: Session = Depends(get_db)):#: #(db: Session = Depends(get_db), limit: int = 10, page: int = 1):
#     ENV_ID = "BalancedSubset-v0"


#     def get_avg_move_time(model_name, specific_env_id=None):
#         """Calculate average move time from observation to action for a model."""
        
#         base_query = (
#             db.query(func.avg(PlayerLog.timestamp_action - PlayerLog.timestamp_observation).label('avg_time'))
#             .join(PlayerGame, PlayerLog.player_game_id == PlayerGame.id)
#             .join(Game, PlayerGame.game_id == Game.id)
#             .filter(
#                 PlayerLog.model_name == model_name,
#                 Game.environment_id == 'BalancedSubset-v0',
#                 PlayerLog.timestamp_action.isnot(None),
#                 PlayerLog.timestamp_observation.isnot(None)
#             )
#         )

#         # Add specific environment filter if provided
#         if specific_env_id is not None:
#             base_query = base_query.filter(Game.specific_env_id == specific_env_id)
            
#         result = base_query.scalar()
#         if result is None:
#             return None
            
#         return round(result, 2)


#     # Get the latest ELO for each model
#     latest_elo_times = (
#         db.query(
#             Elo.model_name,
#             func.max(Elo.updated_at).label('latest_time')
#         )
#         .filter(Elo.environment_id == ENV_ID)
#         .group_by(Elo.model_name)
#         .subquery()
#     )

#     latest_elos = (
#         db.query(
#             Elo.model_name,
#             Elo.elo
#         )
#         .join(
#             latest_elo_times,
#             and_(
#                 Elo.model_name == latest_elo_times.c.model_name,
#                 Elo.updated_at == latest_elo_times.c.latest_time
#             )
#         )
#         .filter(Elo.environment_id == ENV_ID)
#         .order_by(desc(Elo.elo))
#         .offset((page - 1) * limit)  # <-- apply offset for pagination
#         .limit(limit)                 # <-- limit the number of results
#         .subquery()
#     )

#     # Get overall stats for each model
#     model_stats = (
#         db.query(
#             PlayerGame.model_name,
#             func.sum(case((PlayerGame.outcome == 'Win', 1), else_=0)).label('wins'),
#             func.sum(case((PlayerGame.outcome == 'Loss', 1), else_=0)).label('losses'),
#             func.sum(case((PlayerGame.outcome == 'Draw', 1), else_=0)).label('draws')
#         )
#         .join(Game)
#         .filter(
#             Game.environment_id == ENV_ID,
#             Game.status == 'finished'
#         )
#         .group_by(PlayerGame.model_name)
#         .subquery()
#     )


#     def get_game_specific_stats(model_name):
#         stats_dict = {
#             str(i): {
#                 'wins': 0,
#                 'losses': 0,
#                 'draws': 0,
#                 'total_games': 0,
#                 'avg_move_time': get_avg_move_time(model_name, str(i))  # Pass the game ID
#             }
#             for i in range(10)  # Initialize for all possible game IDs
#         }
#         results = (
#             db.query(
#                 Game.specific_env_id,
#                 func.count(PlayerGame.id).label('total_games'),
#                 func.sum(case((PlayerGame.outcome == 'Win', 1), else_=0)).label('wins'),
#                 func.sum(case((PlayerGame.outcome == 'Loss', 1), else_=0)).label('losses'),
#                 func.sum(case((PlayerGame.outcome == 'Draw', 1), else_=0)).label('draws')
#             )
#             .join(PlayerGame, Game.id == PlayerGame.game_id)
#             .filter(
#                 Game.environment_id == ENV_ID,
#                 Game.status == 'finished',
#                 PlayerGame.model_name == model_name,
#                 Game.specific_env_id.isnot(None)
#             )
#             .group_by(Game.specific_env_id)
#             .all()
#         )

#         # Initialize with numeric IDs
#         stats_dict = {
#             str(i): {
#                 'wins': 0,
#                 'losses': 0,
#                 'draws': 0,
#                 'total_games': 0,
#                 'avg_move_time': get_avg_move_time(model_name, str(i))
#             }
#             for i in range(10)  # Initialize for all possible game IDs
#         }
        
#         for stat in results:
#             # Convert environment name to ID if necessary
#             game_id = stat.specific_env_id
#             if game_id in ENV_NAME_TO_ID:
#                 game_id = ENV_NAME_TO_ID[game_id]
#             elif game_id.isdigit():
#                 game_id = str(game_id)
#             else:
#                 continue  # Skip invalid game IDs
                
#             if game_id in stats_dict:
#                 stats_dict[game_id].update({
#                     'wins': stat.wins or 0,
#                     'losses': stat.losses or 0,
#                     'draws': stat.draws or 0,
#                     'total_games': stat.total_games or 0
#                 })
        
#         return stats_dict



#     def get_elo_history(model_name):
#         history = (
#             db.query(Elo)
#             .filter(
#                 Elo.model_name == model_name,
#                 Elo.environment_id == ENV_ID
#             )
#             .order_by(Elo.updated_at)
#             .all()
#         )
#         return [
#             {
#                 "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(h.updated_at)),
#                 "elo": round(h.elo)
#             }
#             for h in history
#         ]

#     def get_recent_games(model_name):
#         return (
#             db.query(PlayerGame.outcome)
#             .join(Game)
#             .filter(
#                 PlayerGame.model_name == model_name,
#                 Game.status == 'finished',
#                 Game.environment_id == ENV_ID
#             )
#             .order_by(desc(Game.started_at))
#             .limit(10)
#             .all()
#         )

#     # Create a subquery to count the number of games per model.
#     game_counts = (
#         db.query(
#             PlayerGame.model_name,
#             func.count(PlayerGame.id).label("game_count")
#         )
#         .group_by(PlayerGame.model_name)
#         .subquery()
#     )

#     # Now join with the elos and model_stats tables and filter by the game_count.
#     combined_data = (
#         db.query(
#             latest_elos.c.model_name,
#             latest_elos.c.elo,
#             model_stats.c.wins,
#             model_stats.c.losses,
#             model_stats.c.draws,
#             game_counts.c.game_count
#         )
#         .join(model_stats, latest_elos.c.model_name == model_stats.c.model_name)
#         .join(game_counts, latest_elos.c.model_name == game_counts.c.model_name)
#         .filter(game_counts.c.game_count >= MIN_GAMES_LEADERBOARD)
#         .order_by(desc(latest_elos.c.elo))
#         .all()
#     )

#     # Get combined data for all models on the current page
#     # combined_data = (
#     #     db.query(
#     #         latest_elos.c.model_name,
#     #         latest_elos.c.elo,
#     #         model_stats.c.wins,
#     #         model_stats.c.losses,
#     #         model_stats.c.draws
#     #     )
#     #     .join(
#     #         model_stats,
#     #         latest_elos.c.model_name == model_stats.c.model_name
#     #     )
#     #     .order_by(desc(latest_elos.c.elo))
#     #     .all()
#     # )

#     # Process results
#     leaderboard = []
#     seen_models = set()  # Track seen models to prevent duplicates
#     rank = (page - 1) * limit + 1  # Adjust rank based on the page

#     for row in combined_data:
#         model_name = row.model_name
        
#         # Skip if we've already seen this model
#         if model_name in seen_models:
#             continue
#         seen_models.add(model_name)

#         game_stats = get_game_specific_stats(model_name)
#         overall_avg_time = get_avg_move_time(model_name)
#         recent_games = get_recent_games(model_name)
#         elo_history = get_elo_history(model_name)

#         total_games = (row.wins or 0) + (row.losses or 0) + (row.draws or 0)
#         win_rate = f"{((row.wins or 0)/total_games * 100 if total_games > 0 else 0):.1f}%"

#         leaderboard.append({
#             "rank": rank,
#             "model_name": model_name,
#             "wins": row.wins or 0,
#             "losses": row.losses or 0,
#             "draws": row.draws or 0,
#             "win_rate": win_rate,
#             "elo": round(row.elo),
#             "recent_games": [game.outcome for game in recent_games],
#             "elo_history": elo_history,
#             "game_specific_stats": game_stats,
#             "total_games": total_games,
#             "avg_move_time": overall_avg_time
#         })
#         rank += 1

#     # Optionally, include pagination info in your response
#     print(leaderboard)
#     print(len(leaderboard))
#     [print(l) for l in leaderboard]
#     # return leaderboard
#     return {
#         "leaderboard": leaderboard,
#         "page": page,
#         "limit": limit,
#         # You might also include total_pages or next_page/prev_page if you compute total count separately
#     }

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