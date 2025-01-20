from typing import List, Tuple, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging, time

# db imports
from core.models import PlayerGame, Elo

# import configs
from config import (
    DEFAULT_ELO, 
    INITIAL_K, HUMAN_K_FACTOR, 
    STANDARD_MODEL_K_FACTOR,
    REDUCED_K, GAMES_THRESHOLD,
    HUMANITY_MODEL_NAME,
    STANDARD_MODELS
)

logger = logging.getLogger(__name__)


def get_dynamic_k(db: Session, model_name: str) -> float:
    """Determine K-factor based on model type and games played."""
    if model_name == HUMANITY_MODEL_NAME:
        return HUMAN_K_FACTOR
    if model_name in STANDARD_MODELS:
        return STANDARD_MODEL_K_FACTOR
    
    games_played = db.query(PlayerGame).filter(PlayerGame.model_name == model_name).count()
    return INITIAL_K if games_played < GAMES_THRESHOLD else REDUCED_K



def update_elos(db: Session, game_id: int, env_id: str):
    players = db.query(PlayerGame).filter(PlayerGame.game_id == game_id).all()
    logger.debug(f"Calculating Elo updates for game '{game_id}' in environment '{env_id}'.")
    current_time = time.time()

    min_reward = min([p.reward for p in players])
    max_reward = max([p.reward for p in players])

    # Gather player details
    player_details = []
    for p in players:
        if p.reward > min_reward:
            outcome = 1  # Win
        elif p.reward < max_reward:
            outcome = 0  # Loss
        else:
            outcome = 0.5  # Draw

        elo_entry = db.query(Elo).filter_by(model_name=p.model_name, environment_id=env_id).order_by(desc(Elo.updated_at)).first()
        prev_elo = elo_entry.elo if elo_entry else DEFAULT_ELO
        k_factor = get_dynamic_k(db, p.model_name)
        player_details.append({
            'model_name': p.model_name,
            'outcome': outcome,
            'prev_elo': prev_elo,
            'k_factor': k_factor
        })

    print(f"\n\n Min: {min_reward}, Max: {max_reward}")
    print(player_details)

    # Calculate average opponent Elo for each player
    for player in player_details:
        opponents = [p for p in player_details if p['model_name'] != player['model_name']]
        if opponents:
            avg_opp_elo = sum([opp['prev_elo'] for opp in opponents]) / len(opponents)
        else:
            avg_opp_elo = DEFAULT_ELO  # Default if no opponents

        expected_score = 1 / (1 + 10 ** ((avg_opp_elo - player['prev_elo']) / 400))
        print(f"Model Name: {player['model_name']}, Outcome: {player['outcome']}, Prev Elo: {player['prev_elo']}, K-factor: {player['k_factor']}, avg Opp elo: {avg_opp_elo}, opponents: {opponents}")
        print(f"expected score: {expected_score}")
        new_elo = player['prev_elo'] + player['k_factor'] * (player['outcome'] - expected_score)
        player['new_elo'] = round(new_elo, 2)
        logger.info(f"Elo Update - {player['model_name']}: {player['prev_elo']} -> {player['new_elo']}")


    print(player_details)
    # Persist Elo updates
    for player in player_details:
        new_elo_entry = Elo(
            model_name=player['model_name'],
            environment_id=env_id,
            elo=player['new_elo'],
            updated_at=current_time
        )
        db.add(new_elo_entry)

    db.commit()
    logger.debug(f"Elo ratings updated for game '{game_id}' in environment '{env_id}'.")
