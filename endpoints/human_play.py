# FastAPI & SlowAPI imports
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address


# db imports
from database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc

# core imports
from core.schemas import HumanMoveRequest
from core.models import HumanPlayer, Matchmaking, Game, PlayerGame, PlayerLog


# import configs
from config import RATE_LIMIT, HUMANITY_MODEL_NAME

# import utilities
import secrets, time, json
from elo_updates import update_elos

# import env handler
from env_handlers import (
    EnvironmentManagerBase,
    OnlineEnvHandler,
    LocalEnvHandler
)


router = APIRouter()
limiter = Limiter(key_func=get_remote_address)



@router.post("/human/register")
def register_human_player(request: Request, db: Session = Depends(get_db)):
    """
    Register a human player using their IP address as identifier.
    """
    print("=== Human Register Endpoint ===")
    print(f"Headers: {dict(request.headers)}")
    print(f"IP: {request.client.host}")
    print(f"Method: {request.method}")
    
    try:
        ip_address = request.client.host
        current_time = time.time()
        
        # Check if IP already exists
        human = db.query(HumanPlayer).filter(HumanPlayer.ip_address == ip_address).first()
        if human:
            print(f"Found existing human with ID: {human.id}")
            human.last_active = current_time
            db.commit()
            return JSONResponse(
                content={"human_id": human.id},
                headers={"Access-Control-Allow-Origin": "http://localhost:3000"}
            )
        
        # Create new human player
        human = HumanPlayer(
            ip_address=ip_address,
            created_at=current_time,
            last_active=current_time
        )
        db.add(human)
        db.commit()
        print(f"Created new human with ID: {human.id}")
        
        return JSONResponse(
            content={"human_id": human.id},
            headers={"Access-Control-Allow-Origin": "http://localhost:3000"}
        )
    except Exception as e:
        print(f"Error in register endpoint: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
            headers={"Access-Control-Allow-Origin": "http://localhost:3000"}
        )


@router.post("/human/join_matchmaking")
def human_join_matchmaking(request: Request, db: Session = Depends(get_db)):
    print("\n=== Human Join Matchmaking Endpoint ===")
    print(f"Request received at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"IP: {request.client.host}")
    
    try:
        ip_address = request.client.host
        
        existing_mm = db.query(Matchmaking).filter(
            Matchmaking.model_name == HUMANITY_MODEL_NAME,
            Matchmaking.human_ip == ip_address
        ).first()
        
        if existing_mm:
            return JSONResponse(
                content={"error": "Already in matchmaking queue"},
                headers={"Access-Control-Allow-Origin": "http://localhost:3000"}
            )

        mm = Matchmaking(
            environment_id="BalancedSubset-v0",
            model_name=HUMANITY_MODEL_NAME,
            joined_at=time.time(),
            time_limit=300,
            last_checked=time.time(),
            is_human=True,
            human_ip=ip_address
        )
        db.add(mm)
        db.commit()
        
        return JSONResponse(
            content={"message": "Added to matchmaking queue"},
            headers={"Access-Control-Allow-Origin": "http://localhost:3000"}
        )
        
    except Exception as e:
        print(f"Error in join matchmaking: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
            headers={"Access-Control-Allow-Origin": "http://localhost:3000"}
        )


@router.get("/human/check_matchmaking_status")
def human_check_matchmaking_status(request: Request, db: Session = Depends(get_db)):
    ip_address = request.client.host

    # 1. Check if you are in matchmaking
    mm = db.query(Matchmaking).filter(
        Matchmaking.is_human == True,
        Matchmaking.human_ip == ip_address
    ).first()
    if mm:
        mm.last_checked = time.time()
        db.commit()
        return {"status": "Searching"}

    # 2. Check if a game has been created for you
    game = db.query(Game).join(PlayerGame).filter(
        PlayerGame.human_ip == ip_address,
        Game.status == "active"
    ).first()

    if game:
        # you have a match
        pg = db.query(PlayerGame).filter(
            PlayerGame.game_id == game.id,
            PlayerGame.human_ip == ip_address
        ).first()

        opponents = db.query(PlayerGame).filter(
            PlayerGame.game_id == game.id,
            PlayerGame.human_ip.is_(None)
        ).all()
        print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++==")
        print(game.id, pg.player_id, ", ".join([o.model_name for o in opponents]) ) 
        print(opponents)
        for opponent in opponents:
            print(opponent, opponent.model_name)
        print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++==")
        return {
            "status": "Match found",
            "game_id": game.id,
            "player_id": pg.player_id,
            "opponent_name": ", ".join([o.model_name for o in opponents]),
            "env_id": game.specific_env_id,
        }

    return {"status": "Not in matchmaking or game"}



@router.get("/human/check_turn")
def human_check_turn(
    request: Request,
    game_id: int = Query(...),   # <-- ensure it’s typed as int
    db: Session = Depends(get_db)
):
    """
    Check the current turn/observation for a human player identified by IP address.
    """
    ip_address = request.client.host
    print(f"[human_check_turn] IP={ip_address}, game_id={game_id}")

    # 1. Find the player game record by ip + game_id
    pg = db.query(PlayerGame).filter(
        PlayerGame.game_id == game_id,
        PlayerGame.human_ip == ip_address
    ).first()
    if not pg:
        raise HTTPException(status_code=404, detail="No active game for this IP")

    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.status != "active":
        return {
            "status": "Game concluded",
            "observation": "Game has ended",
            "done": True
        }

    # 2. Get environment
    env_manager = EnvironmentManagerBase.get_appropriate_manager(game_id, db)
    env = env_manager.get_env(game_id=game_id, env_id="BalancedSubset-v0", db=db)
    
    print(f"Is player turn: {env.check_player_turn(player_id=pg.player_id)}")

    # 3. Check if env concluded
    if env.check_done():
        return {
            "status": "Game concluded",
            "observation": "Game has ended",
            "done": True
        }
    # 4. Check if it's this player's turn
    if env.check_player_turn(player_id=pg.player_id):
        obs = env.get_observation(pg.player_id)
        
        # Log the observation
        log_entry = PlayerLog(
            player_game_id=pg.id,
            model_name=HUMANITY_MODEL_NAME,  # or any label you use for humans
            observation=json.dumps(obs),
            timestamp_observation=time.time()
        )
        db.add(log_entry)
        db.commit()

        return {
            "status": "Your turn",
            "observation": obs,
            "done": env.check_done()
        }
    else:
        return {"status": "Not your turn"}



@router.post("/human/make_move")
def human_make_move(
    payload: HumanMoveRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    ip_address = request.client.host
    game_id = payload.game_id
    move = payload.move

    # 1) Validate the player is in an active game:
    pg = db.query(PlayerGame).join(Game).filter(
        PlayerGame.game_id == game_id,
        PlayerGame.human_ip == ip_address,
        Game.status == "active"
    ).first()
    print(pg)
    if not pg:
        raise HTTPException(status_code=404, detail="Game not found or not active")

    # 2) Check turn
    env_manager = EnvironmentManagerBase.get_appropriate_manager(game_id, db)
    print(env_manager)
    env = env_manager.get_env(game_id=game_id, env_id="BalancedSubset-v0", db=db)
    if not env.check_player_turn(player_id=pg.player_id):
        raise HTTPException(status_code=400, detail="Not your turn")

    # 3) Execute step
    env.execute_step(action=move)
    pg.last_action_time = time.time()
    db.commit()

    # update log
    log_entry = db.query(PlayerLog).filter(
        PlayerLog.player_game_id==pg.id,
        PlayerLog.model_name==pg.model_name
    ).order_by(desc(PlayerLog.timestamp_observation)).first()
    print(pg.id, pg.model_name, log_entry)

    if log_entry:
        log_entry.action = payload.move
        log_entry.timestamp_action = time.time()
        db.commit()

    # 4) Check if game done
    if env.check_done():
        rewards, info = env.extract_results()
        game = db.query(Game).filter(Game.id == game_id).first()
        game.status = "finished"
        game.reason = info.get("reason", "No reason provided")

        for player in db.query(PlayerGame).filter(PlayerGame.game_id == game_id).all():
            player.reward = rewards[player.player_id]
            if player.reward > min(rewards.values()):
                player.outcome = "Win"
            elif player.reward < max(rewards.values()):
                player.outcome = "Loss"
            else:
                player.outcome = "Draw"

        db.commit()
        env_manager.remove_env(game_id)

        # Elo updates
        update_elos(db, game_id, "BalancedSubset-v0")

        return {
            "status": "Game completed",
            "reward": rewards[pg.player_id],
            "reason": info.get("reason", "No reason provided")
        }

    return {"status": "Move accepted", "done": False}



@router.get("/human/get_match_outcome")
def human_get_match_outcome(
    request: Request,
    player_id: int = Query(...),
    game_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """ TODO """
    player_game = db.query(PlayerGame).filter(
        PlayerGame.player_id == player_id,
        PlayerGame.game_id == game_id
    ).first()

    if not player_game:
        raise HTTPException(status_code=404, detail="Player record not found")
    
    # get the outcome
    outcome = player_game.outcome 

    game = db.query(Game).filter(Game.id == game_id).first()

    reason = game.reason

    print(f"\n\n\nOutcome: {outcome}\t Reason: {reason}\n\n\n")

    return {
        "outcome": outcome,
        "reason": reason
    }



@router.get("/human/get_stats")
def get_human_stats(request: Request, db: Session = Depends(get_db)):
    """
    Returns the number of games played, W-L-D, and the last 10 games
    for the current human user, identified by IP address.
    """
    ip_address = request.client.host  # Or request.headers.get('X-Forwarded-For') if behind proxy

    # Check if we know this human
    human_player = db.query(HumanPlayer).filter(HumanPlayer.ip_address == ip_address).first()
    if not human_player:
        # If we don't have a record, return empty stats
        return {
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "recent_games": []
        }

    # Fetch all the PlayerGame rows for this human
    # We assume that we set is_human=True and human_ip=ip_address
    # whenever the human joined/played a game
    player_games = db.query(PlayerGame).join(Game).filter(
        PlayerGame.is_human == True,
        PlayerGame.human_ip == ip_address
    ).order_by(desc(Game.id)).all()

    games_played = len(player_games)
    wins = sum(1 for pg in player_games if pg.outcome == "Win")
    losses = sum(1 for pg in player_games if pg.outcome == "Loss")
    draws = sum(1 for pg in player_games if pg.outcome == "Draw")
    win_rate = wins/games_played if games_played != 0 else 0

    # Get the last 10
    recent_10 = player_games[:10]

    recent_games = []
    for pg in recent_10:
        # environment
        env_id = pg.game.specific_env_id
        # Opponents = same game but is_human=False or different model_name
        # If you have multiple opponents, join them in a single string
        other_players = db.query(PlayerGame).filter(
            PlayerGame.game_id == pg.game_id,
            PlayerGame.id != pg.id
        ).all()
        opp_str = ", ".join([o.model_name for o in other_players])
        
        recent_games.append({
            "environment": env_id,
            "opponent": opp_str if opp_str else "N/A",
            "outcome": pg.outcome if pg.outcome else "Unknown",
        })

    return {
        "games_played": games_played,
        "win_rate": win_rate,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "recent_games": recent_games
    }