# background.py
import time
import threading

# core imports
from core.models import Matchmaking, Environment, Game, PlayerGame, Elo

# import configs
from config import (
    MATCHMAKING_INTERVAL, HUMANITY_MODEL_NAME, STANDARD_MODELS,
    MIN_WAIT_FOR_STANDARD, DEFAULT_ELO
)

# db imports
from database import get_db
from sqlalchemy.orm import Session


# local imports
from matchmaking import matchmaking_algorithm
from timeout_manager import check_and_enforce_timeouts


# logging
import logging
from rich.console import Console 
from rich.table import Table 
from datetime import timedelta

console = Console()
logger = logging.getLogger(__name__)

def matchmaking_loop():
    """
    Continuously runs in the background, checking for matchmaking conditions,
    handling timeouts, etc.
    """
    while True:
        try:
            # Provide a db session
            db_session = next(get_db())

            # handle step timeouts
            check_and_enforce_timeouts(db=db_session)

            # run the matchmaking
            environments = db_session.query(Environment).all()
            for env in environments:
                matchmaking_algorithm(db=db_session, environment=env)

            # log current status
            # log_matchmaking_status(db_session)

            db_session.close()

            # Sleep for your chosen interval
            time.sleep(MATCHMAKING_INTERVAL)

        except Exception as e:
            logger.error(f"Error in matchmaking loop: {e}")
            # To avoid spinning in an error loop, add a brief sleep:
            time.sleep(5)

def start_background_tasks():
    """
    Creates and starts the matchmaking background thread.
    Call this function once from your main startup logic.
    """
    thread = threading.Thread(target=matchmaking_loop, daemon=True)
    thread.start()
    logging.info("Background matchmaking thread started.")



def get_queue_table(db: Session, environment: Environment) -> Table:
    current_time = time.time()
    table = Table(title=f"Queue Status - {environment.environment_id}", header_style="bold magenta")
    table.add_column("Model Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Queue Time", style="yellow")
    table.add_column("Standard?", style="blue")
    table.add_column("Current Elo", style="magenta", justify="right")
    table.add_column("Games Played", style="red", justify="right")

    queued_players = db.query(Matchmaking).filter_by(environment_id=environment.environment_id) \
                       .order_by(Matchmaking.joined_at.asc()).all()

    if not queued_players:
        table.add_row("No players in queue", "-", "-", "-", "-", "-")
        return table

    for player in queued_players:
        # Calculate how long in queue
        time_in_queue = current_time - player.joined_at
        queue_time = str(timedelta(seconds=int(time_in_queue)))

        # Determine player type
        if player.model_name == HUMANITY_MODEL_NAME:
            player_type = "Human"
            standard_status = "Always"
        elif player.model_name in STANDARD_MODELS:
            player_type = "Standard"
            standard_status = "Always"
        else:
            player_type = "Submitted"
            time_until_standard = max(0, MIN_WAIT_FOR_STANDARD - time_in_queue)
            standard_status = "Available" if time_until_standard == 0 \
                                      else f"In {str(timedelta(seconds=int(time_until_standard)))}"

        # Get Elo score and games played
        elo_entry = db.query(Elo).filter_by(model_name=player.model_name,
                                              environment_id=environment.environment_id) \
                         .order_by(Elo.updated_at.desc()).first()
        elo_score = elo_entry.elo if elo_entry else DEFAULT_ELO
        games_played = db.query(PlayerGame).filter(PlayerGame.model_name == player.model_name).count()

        table.add_row(
            player.model_name,
            player_type,
            queue_time,
            standard_status,
            f"{elo_score:.1f}",
            str(games_played)
        )
    return table

def get_active_games_table(db):
    """
    Returns a Rich Table displaying the active games.
    """
    current_time = time.time()

    table = Table(title="Active Games", header_style="bold magenta")
    table.add_column("Game ID", style="cyan", justify="right")
    table.add_column("Environment", style="green")
    table.add_column("Players", style="yellow")
    table.add_column("Duration", style="blue")
    table.add_column("Last Action", style="magenta", justify="right")
    table.add_column("Current Turn", style="red")

    active_games = db.query(Game).filter(Game.status == "active").all()

    if not active_games:
        table.add_row("No active games", "-", "-", "-", "-", "-")
        return table

    for game in active_games:
        players = db.query(PlayerGame).filter(PlayerGame.game_id == game.id) \
                                       .order_by(PlayerGame.player_id).all()
        player_names = []
        last_action_time = None

        for p in players:
            # Append markers for human or standard if needed
            suffix = " (H)" if p.is_human else (" (S)" if p.model_name in STANDARD_MODELS else "")
            player_names.append(p.model_name + suffix)
            if p.last_action_time and (last_action_time is None or p.last_action_time > last_action_time):
                last_action_time = p.last_action_time

        duration = str(timedelta(seconds=int(current_time - game.started_at)))
        last_action = str(timedelta(seconds=int(current_time - last_action_time))) if last_action_time else "Never"

        # In this simplified logging we mark current turn as Unknown (update logic if needed)
        current_turn = "Unknown"

        table.add_row(
            str(game.id),
            game.environment_id,
            " vs ".join(player_names),
            duration,
            last_action,
            current_turn
        )
    return table

def log_matchmaking_status(db):
    """
    Logs the status of matchmaking: both the queue and the active games.
    """
    console.print("\n[bold white on blue]Matchmaking Status[/]\n")

    # Log status for each environment
    environments = db.query(Environment).all()
    for env in environments:
        queue_table = get_queue_table(db, env)
        console.print(queue_table)
    
    # Log active games status
    games_table = get_active_games_table(db)
    console.print(games_table)
    console.print("\n")
