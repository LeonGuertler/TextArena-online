import math, time
from database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, case, label, and_
from core.models import Model, Elo, Game, PlayerGame, PlayerLog
from config import ENV_NAME_TO_ID, DEFAULT_ELO


def categorize_reason(reason: str) -> str:
    """
    Convert the raw 'reason' string into one of: 
    'invalid_move', 'timeout', or 'game_logic'.
    """
    if not reason:
        return "game_logic"
    
    lower = reason.lower()
    if "invalid move" in lower:
        return "invalid_move"
    elif "timed out" in lower or "timeout" in lower:
        return "timeout"
    else:
        return "game_logic"


def get_model(db: Session, model_name: str) -> Model:
    """
    Retrieve a Model row (raises 404 if not found).
    """
    model = db.query(Model).filter(Model.model_name == model_name).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


def get_latest_elo(db: Session, model_name: str, env_id: str):
    return (
        db.query(Elo)
        .filter(Elo.model_name == model_name, Elo.environment_id == env_id)
        .order_by(desc(Elo.updated_at))
        .first()
    )


def get_elo_history(db: Session, model_name: str, env_id: str):
    records = (
        db.query(Elo)
        .filter(Elo.model_name == model_name, Elo.environment_id == env_id)
        .order_by(Elo.updated_at)
        .all()
    )
    return [
        {
            "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(record.updated_at)),
            "elo": round(record.elo),
        }
        for record in records
    ]


def get_recent_games(db: Session, model_name: str, env_id: str, limit: int = 10):
    """
    Returns a list of recent outcomes (e.g. ['Win', 'Loss', 'Win', ...])
    """
    rows = (
        db.query(PlayerGame.outcome)
        .join(Game, Game.id == PlayerGame.game_id)
        .filter(
            PlayerGame.model_name == model_name,
            Game.environment_id == env_id,
            Game.status == 'finished'
        )
        .order_by(desc(Game.started_at))
        .limit(limit)
        .all()
    )
    return [row.outcome for row in rows]


def get_game_stats(db: Session, model_name: str, env_id: str):
    """
    Returns two things:

    1. game_specific_stats: A dict keyed by the environment's specific_env_id
       or some identifier, including:
         - wins, losses, draws, total_games
         - reason_counts[invalid_move/timeout/game_logic] subdivided by total/win/loss/draw
         - avg_move_time
         - invalid_move_loss_rate (where outcome=loss *and* reason=invalid_move)

    2. overall_stats: A dict with total aggregated info (wins, losses, draws, etc).
    """

    # For each finished game by this model in the main environment:
    # We'll gather stats grouped by specific_env_id
    rows = (
        db.query(
            Game.specific_env_id.label("env"),
            PlayerGame.outcome.label("outcome"),
            Game.reason.label("reason"),
        )
        .join(PlayerGame, Game.id == PlayerGame.game_id)
        .filter(
            PlayerGame.model_name == model_name,
            Game.environment_id == env_id,
            Game.status == "finished"
        )
        .all()
    )

    # Prepare a data structure to collect stats
    game_specific_stats: Dict[str, Any] = {}
    # We'll also track an overall total
    overall_stats = {
        "win": 0,
        "loss": 0,
        "draw": 0,
        "total_games": 0,
        # If you want an aggregated reason_counts:
        "reason_counts": {
            "invalid_move": {"total": 0, "win": 0, "loss": 0, "draw": 0},
            "timeout": {"total": 0, "win": 0, "loss": 0, "draw": 0},
            "game_logic": {"total": 0, "win": 0, "loss": 0, "draw": 0},
        },
        "move_times": [],  # if you gather them
    }

    for row in rows:
        env = row.env #or "UnknownEnv"  # fallback if None
        outcome = row.outcome #or "Draw"
        reason_cat = categorize_reason(row.reason)

        if env not in game_specific_stats:
            game_specific_stats[env] = {
                "win": 0,
                "loss": 0,
                "draw": 0,
                "total_games": 0,
                "reason_counts": {
                    "invalid_move": {"total": 0, "win": 0, "loss": 0, "draw": 0},
                    "timeout": {"total": 0, "win": 0, "loss": 0, "draw": 0},
                    "game_logic": {"total": 0, "win": 0, "loss": 0, "draw": 0},
                },
                "move_times": [],  # if you gather them
            }
        
        # Update environment-level tallies
        game_specific_stats[env][outcome.lower()] += 1
        game_specific_stats[env]["total_games"] += 1
        game_specific_stats[env]["reason_counts"][reason_cat]["total"] += 1
        game_specific_stats[env]["reason_counts"][reason_cat][outcome.lower()] += 1

        # Update overall tallies
        overall_stats[outcome.lower()] += 1
        overall_stats["total_games"] += 1
        overall_stats["reason_counts"][reason_cat]["total"] += 1
        overall_stats["reason_counts"][reason_cat][outcome.lower()] += 1

        # get the move times
        pgames = db.query(PlayerLog).filter(
            PlayerLog.model_name == model_name,
            PlayerLog.timestamp_action.isnot(None),
            PlayerLog.timestamp_observation.isnot(None),
        ).join(PlayerGame).filter(
            PlayerLog.player_game_id == PlayerGame.id
        ).join(Game).filter(
            Game.id == PlayerGame.game_id,
            Game.specific_env_id == env
        )

        for game_log in pgames:
            game_specific_stats[env]["move_times"].append(game_log.timestamp_action-game_log.timestamp_observation)
            overall_stats["move_times"].append(game_log.timestamp_action-game_log.timestamp_observation)
        

    # input(game_specific_stats)
    # rename wins, losses and draws
    for env in game_specific_stats.keys():
        # print(game_specific_stats[env])
        game_specific_stats[env]["losses"] = game_specific_stats[env].pop("loss")
        game_specific_stats[env]["wins"] = game_specific_stats[env].pop("win")
        game_specific_stats[env]["draws"] = game_specific_stats[env].pop("draw")

    keys = list(game_specific_stats.keys())
    for env in keys:
        if env in ENV_NAME_TO_ID:
            game_specific_stats[ENV_NAME_TO_ID[env]] = game_specific_stats.pop(env)
        else:
            game_specific_stats[ENV_NAME_TO_ID['unknown']] = game_specific_stats.pop(env)

    overall_stats["losses"] = overall_stats.pop("loss")
    overall_stats["wins"] = overall_stats.pop("win")
    overall_stats["draws"] = overall_stats.pop("draw")

    # Now compute invalid_move_loss_rate, average move time, etc.
    # For the example, let's define invalid_move_loss_rate = (# of losses with reason=invalid_move) / total_games (as a %).

    for env_id_key, env_stats in game_specific_stats.items():
        total_g = env_stats["total_games"]
        if total_g == 0:
            env_stats["avg_move_time"] = None
            env_stats["invalid_move_loss_rate"] = 0
            continue
        
        # If you store logs to compute actual move times, do it here.
        # For brevity we skip that. We'll assume move_times is empty or prefilled.

        # invalid_move_loss_count:
        invalid_move_loss_count = env_stats["reason_counts"]["invalid_move"]["loss"]
        invalid_move_loss_rate = (
            (invalid_move_loss_count / total_g) * 100.0 if total_g else 0
        )
        env_stats["invalid_move_loss_rate"] = round(invalid_move_loss_rate, 2)

        # Example of how you might do average move time if you had logs:
        if env_stats["move_times"]:
            env_stats["avg_move_time"] = round(
                sum(env_stats["move_times"]) / len(env_stats["move_times"]), 2
            )
        else:
            env_stats["avg_move_time"] = None

    # Compute overall stats, e.g. a win_rate, avg_move_time, etc.
    total_g = overall_stats["total_games"]
    if total_g > 0:
        overall_stats["win_rate"] = f"{(overall_stats['wins'] / total_g) * 100:.1f}%"
    else:
        overall_stats["win_rate"] = "N/A"
    
    # Example overall avg_move_time:
    if overall_stats["move_times"]:
        overall_stats["avg_move_time"] = round(
            sum(overall_stats["move_times"]) / len(overall_stats["move_times"]), 2
        )
    else:
        overall_stats["avg_move_time"] = None

    return game_specific_stats, overall_stats


def get_recent_games_details(db: Session, model_name: str, env_id: str, limit: int = 10):
    """
    Returns details for the most recent finished games for the specified model.
    Each item in the returned list includes:
      - environment: the environment ID or a friendly name,
      - opponent: the opponent model's name or 'human' (if applicable),
      - outcome: the outcome for the specified model (e.g. 'Win', 'Loss', 'Draw'),
      - opponent_elo: the opponent's ELO immediately before the game,
      - model_elo: the model's ELO immediately before the game,
      - model_elo_change: the change in the model's ELO across the game.
    """
    import time
    from sqlalchemy import desc

    # Get recent PlayerGame rows for our model.
    player_games = (
        db.query(PlayerGame)
        .join(Game, Game.id == PlayerGame.game_id)
        .filter(
            PlayerGame.model_name == model_name,
            Game.environment_id == env_id,
            Game.status == 'finished',
        )
        .order_by(desc(Game.started_at))
        .limit(limit)
        .all()
    )
    
    game_history = []
    for pg in player_games:
        game = pg.game

        # Get the opponent row: assume opponent is any PlayerGame record from same game.
        opponent_pg = (
            db.query(PlayerGame)
            .filter(
                PlayerGame.game_id == game.id,
                PlayerGame.model_name != model_name  # the other player
            )
            .first()
        )
        
        if opponent_pg:
            opponent = opponent_pg.model_name if opponent_pg.model_name else (opponent_pg.human_ip or "Unknown")
            
            # --- 1. Opponent's ELO before the game ---
            opponent_elo_record = (
                db.query(Elo)
                .filter(
                    Elo.model_name == opponent_pg.model_name,
                    Elo.environment_id == env_id,
                    Elo.updated_at < game.started_at
                )
                .order_by(desc(Elo.updated_at))
                .first()
            )
            opponent_elo = round(opponent_elo_record.elo) if opponent_elo_record else DEFAULT_ELO #None
        else:
            opponent = "N/A"
            opponent_elo = None

        # --- 2. Model's ELO before the game ---
        model_elo_before_record = (
            db.query(Elo)
            .filter(
                Elo.model_name == model_name,
                Elo.environment_id == env_id,
                Elo.updated_at < game.started_at
            )
            .order_by(desc(Elo.updated_at))
            .first()
        )
        model_elo = model_elo_before_record.elo if model_elo_before_record else DEFAULT_ELO #None

        # --- 3. Model's ELO after (or at) the game ---
        model_elo_after_record = (
            db.query(Elo)
            .filter(
                Elo.model_name == model_name,
                Elo.environment_id == env_id,
                Elo.updated_at >= game.started_at
            )
            .order_by(Elo.updated_at)
            .first()
        )
        model_elo_after = model_elo_after_record.elo if model_elo_after_record else DEFAULT_ELO #None

        if (model_elo is not None) and (model_elo_after is not None):
            model_elo_change = round(model_elo_after - model_elo, 2)
        else:
            model_elo_change = None

        game_history.append({
            "environment": game.specific_env_id,  # Or map to a friendly name if desired.
            "opponent": opponent,
            "outcome": pg.outcome,
            "opponent_elo": int(opponent_elo),
            "model_elo": int(model_elo),
            "model_elo_change": int(model_elo_change),
            "started_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(game.started_at)),
        })
    
    return game_history
