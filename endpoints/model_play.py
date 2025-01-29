# FastAPI & SlowAPI imports
from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address


# db imports
from database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, case, label, and_

# core imports
from core.schemas import (
    ModelRegistrationRequest, MatchmakingRegistrationRequest,
    LeaveMatchmakingRequest, StepRequest, GetResultsRequest
)
from core.models import (
    Elo, Model, Game, Environment, Matchmaking, PlayerGame, PlayerLog
)

# import env handlers
from env_handlers import (
    EnvironmentManagerBase,
    OnlineEnvHandler,
    LocalEnvHandler
)

# elo import
from elo_updates import update_elos


# import configs
from config import RATE_LIMIT

# import utilities
import secrets, time, json

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register_model")
@limiter.limit(f"{RATE_LIMIT}/minute")
def register_model(request: Request, payload: ModelRegistrationRequest, db: Session = Depends(get_db)):
    existing = db.query(Model).filter(Model.model_name == payload.model_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Model name exists.")
    model_token = secrets.token_hex(16)
    new_model = Model(model_name=payload.model_name, description=payload.description, email=payload.email, model_token=model_token)
    db.add(new_model)
    db.commit()
    return {"model_token": model_token}

@router.post("/join_matchmaking")
@limiter.limit(f"{RATE_LIMIT}/minute")
def join_matchmaking_endpoint(request: Request, payload: MatchmakingRegistrationRequest, db: Session = Depends(get_db)):
    # confirm model name token env
    m = db.query(Model).filter(Model.model_token == payload.model_token, Model.model_name == payload.model_name).first()
    if not m:
        raise HTTPException(status_code=404, detail="Invalid model token or name.")
    e = db.query(Environment).filter(Environment.environment_id == payload.env_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Invalid environment ID.")
    in_queue = db.query(Matchmaking).filter(Matchmaking.model_name == payload.model_name).first()
    if in_queue:
        raise HTTPException(status_code=400, detail="Already in matchmaking queue.")
    in_game = db.query(PlayerGame).join(Game).filter(
        PlayerGame.model_name == payload.model_name,
        Game.environment_id == payload.env_id,
        Game.status == "active").first()
    if in_game:
        raise HTTPException(status_code=400, detail="Already in an active game.")

    mm = Matchmaking(environment_id=payload.env_id, model_name=payload.model_name,
                     joined_at=time.time(), time_limit=payload.queue_time_limit, last_checked=time.time())
    db.add(mm)
    db.commit()
    return {"message": "Matchmaking request submitted"}

@router.post("/leave_matchmaking")
@limiter.limit(f"{RATE_LIMIT}/minute")
def leave_matchmaking_endpoint(request: Request, payload: LeaveMatchmakingRequest, db: Session = Depends(get_db)):
    """
    Endpoint for a model to leave the matchmaking queue.
    
    Args:
        model_name (str): Name of the model.
        model_token (str): Authentication token for the model.
        env_id (str): Environment ID to leave.
    """
    # Verify model credentials
    m = db.query(Model).filter(Model.model_token == payload.model_token, Model.model_name == payload.model_name).first()
    if not m:
        raise HTTPException(status_code=404, detail="Invalid model token or name.")
    
    # Find and remove the matchmaking entry
    mm = db.query(Matchmaking).filter(
        Matchmaking.model_name == payload.model_name,
        Matchmaking.environment_id == payload.env_id
    ).first()
    
    if not mm:
        raise HTTPException(status_code=404, detail="Model not in matchmaking queue.")
    
    db.delete(mm)
    db.commit()
    
    return {"message": f"Model '{payload.model_name}' has left the matchmaking queue for environment '{payload.env_id}'."}

@router.get("/check_matchmaking_status")
@limiter.limit(f"{RATE_LIMIT}/minute")
def check_matchmaking_status_endpoint(request: Request, env_id: str, model_token: str, model_name: str, db: Session = Depends(get_db)):
    model = db.query(Model).filter(Model.model_token == model_token, Model.model_name == model_name).first()
    if not model:
        raise HTTPException(status_code=404, detail="Invalid model token.")

    mm = db.query(Matchmaking).filter(Matchmaking.model_name == model_name, Matchmaking.environment_id == env_id).first()
    if mm:
        mm.last_checked = time.time()
        db.commit()
        return {"status": "Searching", "queue_time": time.time() - mm.joined_at, "queue_time_limit": mm.time_limit}

    game = db.query(Game).join(PlayerGame).filter(PlayerGame.model_name == model_name, Game.environment_id == env_id, Game.status == "active").first()
    if game:
        pg = db.query(PlayerGame).filter(PlayerGame.game_id == game.id, PlayerGame.model_name == model_name).first()
        opponents = db.query(PlayerGame).filter(PlayerGame.game_id == game.id, PlayerGame.model_name != model_name).all()
        return {
            "status": "Match found",
            "game_id": game.id,
            "player_id": pg.player_id,
            "opponent_name": ", ".join([o.model_name for o in opponents]),
            "num_players": len(opponents) + 1
        }

    raise HTTPException(status_code=404, detail="Not in matchmaking or game.")

@router.get("/check_turn")
@limiter.limit(f"{RATE_LIMIT}/minute")
def check_turn_endpoint(request: Request, env_id: str, model_name: str, model_token: str, game_id: int, player_id: int, db: Session = Depends(get_db)):
    model = db.query(Model).filter(Model.model_token == model_token, Model.model_name == model_name).first()
    if not model:
        raise HTTPException(status_code=404, detail="Invalid model token.")

    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found.")

    pg = db.query(PlayerGame).filter(PlayerGame.game_id == game_id, PlayerGame.model_name == model_name).first()

    if game.status != "active":
        db.query(PlayerGame).filter(
            PlayerGame.model_name == model_name,
            PlayerGame.game_id == game.id
        ).first()
        env_manager = EnvironmentManagerBase.get_appropriate_manager(game_id, db)
        env = env_manager.get_env(game_id=game_id, env_id="BalancedSubset-v0", db=db)

        obs = env.force_get_observation(pg.player_id)
        # obs = env.get_observation(pg.
        ### get player game)
        if obs:
            log_entry = PlayerLog(player_game_id=pg.id, model_name=pg.model_name, 
                            observation=json.dumps(obs), timestamp_observation=time.time())
            db.add(log_entry)
            db.commit()
            return {"status": "Game concluded", "observation": obs, "done": True}
            # return {"status": "Game concluded", "observation": [[-1, "Game concluded"]], "done": True}
        else:
            return {"status": "Game concluded", "observation": [[-1, "Game concluded"]], "done": True}

    if player_id != pg.player_id:
        raise HTTPException(status_code=404, detail="Player ID mismatch.")

    pg.last_action_time = time.time()
    db.commit()

    env_manager = EnvironmentManagerBase.get_appropriate_manager(game_id, db)
    env = env_manager.get_env(game_id=game_id, env_id=env_id, db=db)
    
    if env.check_player_turn(player_id=player_id):
        obs = env.get_observation(player_id)
        log_entry = PlayerLog(player_game_id=pg.id, model_name=pg.model_name, 
                            observation=json.dumps(obs), timestamp_observation=time.time())
        db.add(log_entry)
        db.commit()
        return {"status": "Your turn", "game_id": game_id, "observation": obs, "done": env.check_done()}
    else:
        return {"status": "Not your turn"}


@router.post("/step")
@limiter.limit(f"{RATE_LIMIT}/minute")
def step_endpoint(request: Request, payload: StepRequest, db: Session = Depends(get_db)):
    model = db.query(Model).filter(
        Model.model_token == payload.model_token, 
        Model.model_name == payload.model_name
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail="Invalid model token.")

    pg = db.query(PlayerGame).join(Game).filter(
        PlayerGame.model_name == payload.model_name,
        Game.status == "active",
        Game.id == payload.game_id
    ).first()

    if not pg:
        finished_pg = db.query(PlayerGame).join(Game).filter(
            PlayerGame.model_name == payload.model_name,
            Game.id == payload.game_id,
            Game.status == "finished"
        ).first()
        if finished_pg:
            return {"message": "Game concluded.", "done": True}
        raise HTTPException(status_code=404, detail="No active game found.")

    pg.last_action_time = time.time()
    db.commit()

    if payload.game_id != pg.game_id:
        raise HTTPException(status_code=404, detail="Game ID mismatch.")


    env_manager = EnvironmentManagerBase.get_appropriate_manager(payload.game_id, db)
    env = env_manager.get_env(game_id=payload.game_id, env_id=payload.env_id, db=db)
    
    if env.check_player_turn(player_id=pg.player_id):
        env.execute_step(action=payload.action_text)
        log_entry = db.query(PlayerLog).filter(
            PlayerLog.player_game_id==pg.id, 
            PlayerLog.model_name==pg.model_name
        ).order_by(desc(PlayerLog.timestamp_observation)).first()
        
        if log_entry:
            log_entry.action = payload.action_text
            log_entry.timestamp_action = time.time()
            db.commit()

        done = env.check_done()
        if done:
            rewards, info = env.extract_results()
            game = db.query(Game).filter(Game.id == payload.game_id).first()
            if game:
                game.status = "finished"
                game.reason = info.get("reason", "No reason provided")
                
            env_manager.remove_env(payload.game_id)

            players = db.query(PlayerGame).filter(PlayerGame.game_id == payload.game_id).all()
            min_reward = min([rewards[player.player_id] for player in players])
            max_reward = max([rewards[player.player_id] for player in players])
            
            for player in players:
                player.reward = rewards[player.player_id]
                if player.reward > min_reward:
                    player.outcome = "Win"
                elif player.reward < max_reward:
                    player.outcome = "Loss"
                else:
                    player.outcome = "Draw"
            
                db.commit()
                
            update_elos(db, payload.game_id, game.environment_id)

        return {"message": "Action submitted.", "done": done}
    else:
        raise HTTPException(status_code=400, detail="Not your turn.")


@router.post("/get_results")
@limiter.limit(f"{RATE_LIMIT}/minute")
def get_results_endpoint(request: Request, payload: GetResultsRequest, db: Session = Depends(get_db)):
    pg = db.query(PlayerGame).filter(PlayerGame.game_id == payload.game_id, PlayerGame.model_name == payload.model_name).first()
    if not pg:
        raise HTTPException(status_code=404, detail="Game not found.")

    reward = pg.reward
    elo_scores = db.query(Elo).filter(Elo.model_name==payload.model_name, Elo.environment_id==payload.env_id).order_by(desc(Elo.updated_at)).limit(2).all()
    if not elo_scores:
        raise HTTPException(status_code=404, detail="No elo scores.")

    elos = [e.elo for e in elo_scores]
    if len(elos) == 1:
        current_elo_score = elos[0]
        prev_elo_score = None
    else:
        current_elo_score, prev_elo_score = elos[0], elos[1]

    player_games = db.query(PlayerGame).filter(PlayerGame.game_id == payload.game_id).all()
    opponents = [p.model_name for p in player_games if p.model_name != payload.model_name]

    outcome = "Win" if reward > 0 else ("Draw" if reward == 0 else "Loss")
    reason = db.query(Game).filter(Game.id == payload.game_id).first().reason

    return {
        "reward": reward,
        "reason": reason,
        "prev_elo_score": prev_elo_score,
        "current_elo_score": current_elo_score,
        "opponent_names": ", ".join(opponents),
        "outcome": outcome
    }


