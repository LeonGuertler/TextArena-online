from typing import List, Tuple, Dict
from sqlalchemy import delete, or_
from sqlalchemy.orm import Session
import time
import logging 

# db imports
from core.models import Game, PlayerGame, PlayerLog, Matchmaking

# import configs
from config import STEP_TIMEOUT, MATCHMAKING_INACTIVITY_TIMEOUT

# local imports
from elo_updates import update_elos

logger = logging.getLogger(__name__)

def handle_action_timeout(db: Session, game_id: int, model_name: str):
    # Query all PlayerGame records with reward == None for the given game_id
    players = db.query(PlayerGame).filter(
        PlayerGame.game_id == game_id,
        PlayerGame.reward == None
    ).all()

    # Separate opponents and player based on model_name
    opponents = [pg for pg in players if pg.model_name != model_name]
    player = next((pg for pg in players if pg.model_name == model_name), None)

    game = db.query(Game).filter(Game.id == game_id).first()
    player.reward = -1 # Timed-out player loses
    player.outcome = "Loss"
    for opp in opponents:
        opp.reward = 0 # counted as win
        opp.outcome = "Win"

    game.status = "finished"
    game.reason = f"Player '{model_name}' timed out."

    db.commit()
    logger.info(f"Player '{player.model_name}' in game '{game.id}' timed out. Game concluded.")

    # Update Elo ratings
    update_elos(db, game.id, game.environment_id)


def handle_matchmaking_timeout(db: Session, matchmaking_id: int):
    deletion_row = db.query(Matchmaking).filter(Matchmaking.id == matchmaking_id).first()
    db.delete(deletion_row)
    db.commit()

def check_and_enforce_timeouts(db: Session):
    # check in-game timeouts
    for game in db.query(Game).filter(Game.status == "active").all():
        # get the relevant player Games
        for pgame in db.query(PlayerGame).filter(PlayerGame.game_id == game.id).all():
            for plog in db.query(PlayerLog).filter(
                PlayerLog.player_game_id == pgame.id,
                PlayerLog.timestamp_observation.isnot(None),
                PlayerLog.timestamp_action.is_(None)).all():
                # Check if timed out
                if (time.time() - plog.timestamp_observation) > STEP_TIMEOUT:
                    # timed out
                    handle_action_timeout(
                        db=db,
                        game_id=game.id,
                        model_name=plog.model_name
                    )

    # check for game-not-loading timeouts (i.e. env initted, but no observations)
    for pg in db.query(PlayerGame).filter(PlayerGame.outcome.is_(None)).all():
        # check for player logs
        player_logs = db.query(PlayerLog).filter(PlayerLog.player_game_id == pg.id).all()
        if len(player_logs) == 0 and (time.time() - pg.last_action_time) > STEP_TIMEOUT:
            # simply set game status to failed
            failed_game = db.query(Game).filter(Game.id == pg.game_id).first()
            failed_game.status = "failed"
    
    db.commit()


    # check queue timeouts
    for queue_item in db.query(Matchmaking).filter():
        # remove those where last_checked has timed out
        print(time.time() - queue_item.last_checked)
        if (time.time() - queue_item.last_checked) > MATCHMAKING_INACTIVITY_TIMEOUT:
            handle_matchmaking_timeout(
                db=db,
                matchmaking_id=queue_item.id
            )