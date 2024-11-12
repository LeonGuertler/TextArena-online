# main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
import secrets
import time
import json

from schemas import (
    ModelRegistrationRequest,
    MatchmakingRegistrationRequest,
    StepRequest,
    GetResultsRequest
)
from models import Model, Base, Environment, Matchmaking, PlayerGame, Game, Elo, PlayerLog
from config import DATABASE_URL, K, DEFAULT_ELO, MATCHMAKING_INACTIVITY_TIMEOUT, STEP_TIMEOUT
from database import engine, get_db
import register_environments
from environment_manager import EnvironmentManager  # Import the EnvironmentManager
from typing import Tuple, Dict

app = FastAPI()

# Create all tables in the database
Base.metadata.create_all(bind=engine)

# register all environments
register_environments.register_envs()

def confirm_model_name_token_env(model_name: str, model_token: str, env_id: str, db: Session):
    """
    Confirm that the model name and token are valid and the environment exists.

    Args:
        model_name (str): Name of the model.
        model_token (str): Authentication token for the model.
        env_id (str): Environment ID.
        db (Session): Database session.

    Raises:
        HTTPException: If validation fails.
    """
    # Check that the model exists and matches the model_name
    model = db.query(Model).filter(
        Model.model_token == model_token,
        Model.model_name == model_name
    ).first()

    if not model:
        raise HTTPException(status_code=404, detail="Invalid model token or model name.")

    # Check that env_id exists in the Environment table
    environment = db.query(Environment).filter(
        Environment.environment_id == env_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Invalid environment ID.")

def get_current_game_id(model_name: str, db: Session) -> Tuple[int, int]:
    """
    Retrieve the current active game ID and player ID for the model.

    Args:
        model_name (str): Name of the model.
        db (Session): Database session.

    Returns:
        Tuple[int, int]: Game ID and Player ID.

    Raises:
        HTTPException: If no active game is found.
    """
    # Find the active game for this model and environment
    player_game = db.query(PlayerGame).join(Game).filter(
        PlayerGame.model_name == model_name,
        Game.status == "active"
    ).first()

    if not player_game:
        raise HTTPException(status_code=404, detail="No active game found for this model and environment.")

    return player_game.game_id, player_game.player_id

@app.post("/register_model")
def register_model(
    request: ModelRegistrationRequest,
    db: Session = Depends(get_db)
):
    """
    Endpoint to register a new model.

    Args:
        request (ModelRegistrationRequest): Model registration data.
        db (Session): Database session.

    Returns:
        dict: Contains the model_token.
    """
    # Check if the model_name is unique
    existing_model = db.query(Model).filter(
        Model.model_name == request.model_name
    ).first()

    if existing_model:
        raise HTTPException(
            status_code=400, 
            detail="Model name already exists."
        )

    # Generate a secure model_token 
    model_token = secrets.token_hex(16)

    # Create a new Model instance
    new_model = Model(
        model_name=request.model_name,
        description=request.description,
        email=request.email,
        model_token=model_token
    )

    # Add and commit to the database
    db.add(new_model)
    db.commit()
    db.refresh(new_model)  # Refresh to get the model detail after commit

    # Return the model token in the response
    return {"model_token": model_token}

@app.post("/join_matchmaking")
def join_matchmaking_endpoint(
    request: MatchmakingRegistrationRequest,
    db: Session = Depends(get_db)
):
    """
    Endpoint to join the matchmaking queue.

    Args:
        request (MatchmakingRegistrationRequest): Matchmaking data.
        db (Session): Database session.

    Returns:
        dict: Confirmation message.
    """
    model_name = request.model_name 
    model_token = request.model_token 
    env_id = request.env_id 
    queue_time_limit = request.queue_time_limit

    # Validate model and environment
    confirm_model_name_token_env(
        model_name=model_name,
        model_token=model_token,
        env_id=env_id,
        db=db
    )

    # Check if the model is already in matchmaking or in a game 
    existing_matchmaking = db.query(Matchmaking).filter(
        Matchmaking.model_name == model_name,
    ).first()
    if existing_matchmaking:
        raise HTTPException(status_code=400, detail="Model is already in matchmaking queue.")

    # Check if the model is already in an active game 
    existing_game = db.query(PlayerGame).join(Game).filter(
        PlayerGame.model_name == model_name,
        Game.environment_id == env_id,
        Game.status == "active"
    ).first()
    if existing_game:
        raise HTTPException(status_code=400, detail="Model is already in an active game.")

    print(env_id, model_name, time.time(), queue_time_limit)
    # Add model to matchmaking queue 
    matchmaking_entry = Matchmaking(
        environment_id=env_id,
        model_name=model_name,
        joined_at=time.time(),
        time_limit=queue_time_limit,
        last_checked=time.time()
    )

    # Add and commit to the database
    db.add(matchmaking_entry)
    db.commit()
    db.refresh(matchmaking_entry)

    return {"message": "Matchmaking request submitted"}

@app.get("/check_matchmaking_status")
def check_matchmaking_status_endpoint(
    env_id: str, 
    model_token: str,
    model_name: str,
    db: Session = Depends(get_db)
):
    """
    Endpoint to check the matchmaking status of a model.

    Args:
        env_id (str): Environment ID.
        model_token (str): Model authentication token.
        db (Session): Database session.

    Returns:
        dict: Status of matchmaking and game details if matched.
    """
    # Retrieve the model associated with the token
    model = db.query(Model).filter(
        Model.model_token == model_token,
        Model.model_name == model_name,
    ).first()

    if not model:
        raise HTTPException(status_code=404, detail="Invalid model token.")

    # Update the last_checked timestamp
    matchmaking_entry = db.query(Matchmaking).filter(
        Matchmaking.model_name == model_name,
        Matchmaking.environment_id == env_id
    ).first()

    if matchmaking_entry:
        matchmaking_entry.last_checked = time.time()
        db.commit()

    # Check if the model is in matchmaking for the specific environment
    matchmaking_entry = db.query(Matchmaking).filter(
        Matchmaking.model_name == model_name,
        Matchmaking.environment_id == env_id
    ).first()

    if matchmaking_entry:
        return {
            "status": "Searching",
            "queue_time": time.time() - matchmaking_entry.joined_at,
            "queue_time_limit": matchmaking_entry.time_limit,
            }

    # Check if the model is in a matched game
    game = db.query(Game).join(PlayerGame).filter(
        PlayerGame.model_name == model_name,
        Game.environment_id == env_id,
        Game.status == "active"
    ).first()

    if game:
        player_game = db.query(PlayerGame).filter(
            PlayerGame.game_id == game.id,
            PlayerGame.model_name == model_name
        ).first()
        opponent_player_games = db.query(PlayerGame).filter(
            PlayerGame.game_id == game.id,
            PlayerGame.model_name != model_name
        ).all()
        num_players = len(opponent_player_games) + 1
        opponent_str = ", ".join([opp.model_name for opp in opponent_player_games])
        return {
            "status": "Match found", 
            "game_id": game.id, 
            "player_id": player_game.player_id,
            "opponent_name": opponent_str,
            "num_players": num_players
        }

    # If not found in matchmaking or games
    raise HTTPException(status_code=404, detail="Model is not in matchmaking queue or in a game.")

@app.get("/check_turn")
def check_turn_endpoint(
    env_id: str,
    model_name: str,
    model_token: str,
    game_id: int,
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Endpoint to check if it's the model's turn in the current game.

    Args:
        env_id (str): Environment ID.
        model_token (str): Model authentication token.
        db (Session): Database session.

    Returns:
        dict: Turn status and observations if it's the model's turn.
    """

    # Retrieve the model associated with the token
    model = db.query(Model).filter(Model.model_token == model_token).first()
    if not model:
        raise HTTPException(status_code=404, detail="Invalid model token.")

    model_name = model.model_name

    # Find the game for this model
    game = db.query(Game).filter(
        Game.id == game_id,
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found.")

    # if the game is not active, return that information
    if game.status != "active":
        return {
            "status": "Game concluded",
            "observations": {player_id: [[-1, "Game has already concluded. You won."]]},
            "done": True # just to double confirm
        }

    # get the player id 
    player_game = db.query(PlayerGame).filter(
        PlayerGame.game_id == game_id,
        PlayerGame.model_name == model_name,
    ).first()

    # confirm player id
    # print(player_id, player_game.player_id)
    if not player_id == player_game.player_id:
        raise HTTPException(status_code=404, detail="The player ids don't match as expected.")

    # Update the last_action_time to track step timeout
    player_game.last_action_time = time.time()
    db.commit()

    # Retrieve the existing environment handler
    game_handler = EnvironmentManager.get_env(game_id=game_id, env_id=env_id)

    # print(player_id, game_handler.env.state.current_player)

    # Check if it's the player's turn
    if game_handler.check_player_turn(player_id=player_id):
        observations = game_handler.get_observation(player_id=player_id)
        # Log the observation
        log_entry = PlayerLog(
            player_game_id=player_game.id,
            model_name=player_game.model_name,
            observation=json.dumps(observations),
            timestamp_observation=time.time()
        )
        db.add(log_entry)
        db.commit()
        return {
            "status": "Your turn",
            "game_id": game_id,
            "observations": observations,
            "done": game_handler.check_done()
        }
    else:
        return {"status": "Not your turn"}

@app.post("/step")
def step_endpoint(
    request: StepRequest,
    db: Session = Depends(get_db)
):
    """
    Endpoint to submit a step/action in the game.

    Args:
        request (StepRequest): Request containing model_token and action.
        db (Session): Database session.

    Returns:
        dict: Confirmation of action submission or error.
    """
    model_token = request.model_token
    model_name = request.model_name 
    action = request.action_text
    game_id = request.game_id

    # Retrieve the model associated with the token
    model = db.query(Model).filter(
        Model.model_token == model_token,
        Model.model_name == model_name
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail="Invalid model token.")

    # Retrieve the active game and player ID
    player_game = db.query(PlayerGame).join(Game).filter(
        PlayerGame.model_name == model_name,
        Game.status == "active",
        Game.id == game_id
    ).first()

    if not player_game:
        # check if the game has concluded
        player_game = db.query(PlayerGame).join(Game).filter(
            PlayerGame.model_name == model_name,
            Game.id == game_id,
            Game.status == "finished"
        )
        if player_game:
            return {"message": "The games has already concluded.", "done": True}
        else:
            raise HTTPException(status_code=404, detail="No active game found for this model.")

    # Update last_action_time
    player_game.last_action_time = time.time()
    db.commit()

    # confirm the game id matches
    if game_id != player_game.game_id:
        raise HTTPException(status_code=404, detail="Game id does not match.")

    player_id = player_game.player_id
    env_id = player_game.game.environment_id

    # Retrieve the existing environment handler
    game_handler = EnvironmentManager.get_env(game_id=game_id, env_id=env_id)

    # Confirm it is the player's turn
    if game_handler.check_player_turn(player_id=player_id):
        # Execute the player's action
        game_handler.execute_step(player_id=player_id, action=action)
        
        # update the most recent log entry with the action
        log_entry = db.query(PlayerLog).filter(
            PlayerLog.player_game_id==player_game.id,
            PlayerLog.model_name==player_game.model_name,
        ).order_by(desc(PlayerLog.timestamp_observation)).first()
        log_entry.action = action
        log_entry.timestamp_action = time.time()
        db.commit()

        # Check if the game is done and clean up if necessary
        if game_handler.check_done():
            rewards, info = game_handler.extract_results()
            # Update game status in the database
            game = db.query(Game).filter(Game.id == game_id).first()
            if game:
                game.status = "finished"
                game.reason = game_handler.info.get("reason", "No reason provided")
                db.commit()

            EnvironmentManager.remove_env(game_id)
            # for both models, set the appropriate reward
            players = db.query(PlayerGame).filter(
                PlayerGame.game_id == game_id
            ).all()
            for player in players:
                player.reward = rewards[player.player_id]
                db.commit()

            # calculate the updated elo for all players

            # 1. extract all participating players, their previous elos, and whether they won
            player_games = db.query(PlayerGame).filter(
                PlayerGame.game_id == game_id
            ).all()
            player_game_details = []
            for player_game_entry in player_games:
                # get model name 
                model_name_pg = player_game_entry.model_name

                # get outcome
                outcome = (player_game_entry.reward + 1) / 2  # {0, 0.5, 1}

                # get previous elo score
                elo_entry = db.query(Elo).filter(
                    Elo.model_name == model_name_pg, 
                    Elo.environment_id == env_id
                ).order_by(desc(Elo.updated_at)).first()

                if not elo_entry:
                    prev_elo = DEFAULT_ELO
                else:
                    prev_elo = elo_entry.elo

                player_game_details.append(
                    (model_name_pg, outcome, prev_elo)
                )

            # update the elo for all players
            # for each player, we compare it to the average opponent elo
            updated_elos = []
            print(player_game_details)
            for model_name_pg, outcome, prev_elo in player_game_details:
                opp_elos = [elo for mn, oc, elo in player_game_details if mn != model_name_pg]
                if opp_elos:
                    opp_elo = sum(opp_elos) / len(opp_elos)
                else:
                    opp_elo = DEFAULT_ELO  # Default if no opponents

                # expected score for player
                expected_outcome = 1 / (1 + 10**((opp_elo - prev_elo)/400))
                print(model_name_pg, outcome, prev_elo, expected_outcome, outcome-expected_outcome, K*(outcome-expected_outcome))
                updated_elo = prev_elo + K * (outcome - expected_outcome)
                updated_elos.append(
                    (model_name_pg, updated_elo)
                )

            # Save updated Elo ratings to the database
            for model_name_pg, elo in updated_elos:
                new_elo_entry = Elo(
                    model_name=model_name_pg,
                    environment_id=env_id,
                    elo=elo,
                    updated_at=time.time()
                )
                db.add(new_elo_entry)

            db.commit()

        # Start step timeout timer
        player_game.last_action_time = time.time()
        db.commit()

        return {"message": "Action submitted successfully.", "done": game_handler.check_done()}
    else:
        raise HTTPException(status_code=400, detail="It's not your turn.")

@app.post("/get_results")
def get_results_endpoint(
    request: GetResultsRequest,
    db: Session = Depends(get_db)
):
    game_id = request.game_id 
    model_name = request.model_name 
    env_id = request.env_id

    # get the reward
    player_game = db.query(PlayerGame).filter(
        PlayerGame.game_id == game_id,
        PlayerGame.model_name == model_name
    ).first()
    if not player_game:
        raise HTTPException(status_code=404, detail="Game not found.")

    reward = player_game.reward 

    # get the two most recent elo scores
    elo_scores = db.query(Elo).filter(
        Elo.model_name == model_name,
        Elo.environment_id == env_id
    ).order_by(desc(Elo.updated_at)).limit(2).all()

    if not elo_scores:
        raise HTTPException(status_code=404, detail="Can't find elo scores.")

    elo_scores_sorted = sorted([(elo_score.elo, elo_score.updated_at) for elo_score in elo_scores], key=lambda x: x[1], reverse=True)
    
    if len(elo_scores_sorted) == 1:
        prev_elo_score = None 
        current_elo_score = elo_scores_sorted[0][0]
    else:
        current_elo_score, prev_elo_score = [elo[0] for elo in elo_scores_sorted[:2]]

    # get the opponent model name 
    player_games = db.query(PlayerGame).filter(
        PlayerGame.game_id == game_id
    ).all()
    opponent_names = [pg.model_name for pg in player_games if pg.model_name != model_name]

    

    # get outcome string
    if reward < 0:
        outcome = "Loss"
    elif reward == 0:
        outcome = "Draw"
    elif reward > 0:
        outcome = "Win"

    # get the reason
    reason = db.query(Game).filter(
        Game.id == game_id
    ).first().reason

    return {
        "reward": reward,
        "reason": reason,
        "prev_elo_score": prev_elo_score,
        "current_elo_score": current_elo_score,
        "opponent_names": ", ".join(opponent_names),  # to accommodate for multi-player
        "outcome": outcome
    }

