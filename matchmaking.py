
from typing import List, Tuple, Dict
import logging
from rich.table import Table

# matchmaking imports
import time, random
import numpy as np
from itertools import combinations

# db imports
from sqlalchemy import desc
from sqlalchemy.sql import and_
from sqlalchemy.orm import Session

# core imports
from core.models import (
    Model, Matchmaking, Elo, Environment, Game, 
    PlayerGame, PlayerLog, HumanPlayer
)

# import configs
from config import (
    HUMANITY_MODEL_NAME, STANDARD_MODELS,
    MIN_WAIT_FOR_STANDARD, MAX_ELO_DELTA,
    PCT_TIME_BASE, NUM_RECENT_GAMES_CAP,
    DEFAULT_ELO
)

# import env handlers
from env_handlers import (
    EnvironmentManagerBase,
    OnlineEnvHandler,
    LocalEnvHandler
)

logger = logging.getLogger(__name__)

# def get_recency_count(db: Session, model1: str, model2: str, window: int = 7 * 86400) -> int:
def get_recency_count(db: Session, model1: str, model2: str, window: int = 3*3600) -> int:
    """Count recent matches between two models."""
    current_time = time.time()
    count = db.query(Game).join(PlayerGame, Game.id == PlayerGame.game_id).filter(
        Game.started_at >= (current_time - window),
        PlayerGame.model_name.in_([model1, model2])
    ).group_by(Game.id).having(
        and_(
            PlayerGame.model_name == model1,
            PlayerGame.model_name == model2
        )
    ).count()
    return count

def compute_match_score(db: Session, combo: List[Dict]) -> float:
    """limited to two players"""
    model_a, model_b = combo

    # check if they have the same email
    if model_a["email"] == model_b["email"]:
        return 0 

    # Check for standard models and humans
    model_a["human"] = model_a["model_name"] == HUMANITY_MODEL_NAME
    model_b["human"] = model_b["model_name"] == HUMANITY_MODEL_NAME
    has_human = model_a["human"] or model_b["human"]
    # if has_human:
    #     return 0
    
    model_a["standard"] = model_a["model_name"] in STANDARD_MODELS
    model_b["standard"] = model_b["model_name"] in STANDARD_MODELS
    has_standard = model_a["standard"] or model_b["standard"]
    
    # If any player has been waiting for less than standard model time limit
    # and one of them is a standard model, leave
    if has_standard and not has_human:
        if not any(t > MIN_WAIT_FOR_STANDARD for t in [model_a["time_in_queue"], model_b["time_in_queue"]]):
            return 0 

    # check for elo diff limit
    elo_delta = abs(model_a["elo"] - model_b["elo"])
    if elo_delta > MAX_ELO_DELTA:
        return 0 

    # get the number of recent matches
    recent_match_count = get_recency_count(db, model_a["model_name"], model_b["model_name"])


    elo_component = (1 - (elo_delta/MAX_ELO_DELTA))**2     # [0, 1]
    time_component = PCT_TIME_BASE + (max([model_a["pct_queue"], model_b["pct_queue"]])*(1-PCT_TIME_BASE)) # [0.5, 1]
    recent_matches_component = 1 - (min([recent_match_count, NUM_RECENT_GAMES_CAP]) / (NUM_RECENT_GAMES_CAP*2)) # [0.5, 1]
    return elo_component * time_component * recent_matches_component


def matchmaking_algorithm(db: Session, environment: Environment):
    """Core matchmaking algorithm with support for humans and standard models."""
    # logger.info(f"Starting matchmaking for environment '{environment.environment_id}'.")
    current_time = time.time()

    # Get queued players
    queued_players = db.query(Matchmaking).filter_by(
        environment_id=environment.environment_id
    ).order_by(Matchmaking.joined_at.asc()).all()

    # Prepare player data
    player_data = []
    for p in queued_players:
        elo_entry = db.query(Elo).filter_by(
            model_name=p.model_name, 
            environment_id=environment.environment_id
        ).order_by(desc(Elo.updated_at)).first()
        
        elo_score = elo_entry.elo if elo_entry else DEFAULT_ELO
        time_in_queue = current_time - p.joined_at

        # get email
        email = db.query(Model).filter_by(
            model_name=p.model_name,
        ).first().email
        
        player_data.append({
            'matchmaking': p,
            'model_name': p.model_name,
            'email': email,
            'elo': elo_score,
            'time_in_queue': time_in_queue,
            'pct_queue': time_in_queue / p.time_limit
        })

    # add standard models
    for model_name in STANDARD_MODELS:
        elo_entry = db.query(Elo).filter_by(
            model_name=model_name,
            environment_id=environment.environment_id
        ).order_by(desc(Elo.updated_at)).first()

        elo_score = elo_entry.elo if elo_entry else DEFAULT_ELO
        player_data.append({
            'matchmaking': None,
            'model_name': model_name,
            'email': " ", # empty placeholder for email matching
            'elo': elo_score,
            'time_in_queue': -1,
            'pct_queue': 0
        })

    # shuffle
    random.shuffle(player_data)


    # Generate and score combinations
    possible_combinations = list(combinations(player_data, environment.num_players))
    scored_combinations = [
        (compute_match_score(db, combo), combo)
        for combo in possible_combinations
    ]
    scored_combinations.sort(key=lambda x: x[0], reverse=True)
    print(scored_combinations)

    # Select matches
    selected_players = set()
    final_matches = []
    
    for match_prob, combo in scored_combinations:
        models = [player['model_name'] for player in combo]
        if any(model in selected_players for model in models):
            continue

        # try matching
        if np.random.uniform() < match_prob:
            selected_players.update(models)
            final_matches.append(combo)

    # Create games
    for match in final_matches:
        game_id = create_game(db, match, environment)
        
        # Log match details
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Player ID", style="dim", width=12)
        table.add_column("Model Name", style="dim", width=30)
        table.add_column("Type", style="dim", width=20)
        
        for pg in db.query(PlayerGame).filter_by(game_id=game_id).all():
            player_type = "Human" if pg.is_human else (
                "Standard" if pg.model_name in STANDARD_MODELS else "Submitted"
            )
            table.add_row(str(pg.player_id), pg.model_name, player_type)
            
        # logger.info(f"Created game {game_id}:\n{table}")



def create_game(db: Session, match: List[Dict], environment: Environment) -> int:
    """Create a new game with appropriate environment manager."""
    current_time = time.time()
    
    # Create game record
    game = Game(
        environment_id=environment.environment_id,
        started_at=current_time,
        status="active"
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    
    # Add players to game first
    for idx, player in enumerate(match):
        pg = PlayerGame(
            game_id=game.id,
            model_name=player['model_name'],
            player_id=idx,
            last_action_time=current_time,
            is_human=player['model_name'] == HUMANITY_MODEL_NAME,
            human_ip=player['matchmaking'].human_ip if player['model_name'] == HUMANITY_MODEL_NAME else None
        )
        db.add(pg)
        if player['matchmaking'] is not None:
            db.delete(player['matchmaking'])
    db.commit()
    
    # Now initialize the appropriate environment
    env_manager = EnvironmentManagerBase.get_appropriate_manager(game.id, db)
    env = env_manager.get_env(game_id=game.id, env_id=environment.environment_id, db=db)

    game.specific_env_id = env.env_id 
    db.commit()

    return game.id