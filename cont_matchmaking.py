# cont_matchmaking.py
from database import get_db 
from models import (
    Model, Matchmaking, Elo, 
    Environment, Game, PlayerGame, PlayerLog
)
import time
from itertools import combinations
from sqlalchemy.orm import Session
from sqlalchemy import desc
from environment_manager import EnvironmentManager  # Import EnvironmentManager
import threading
from tabulate import tabulate  # Import tabulate for pretty printing
from config import MATCHMAKING_INACTIVITY_TIMEOUT, STEP_TIMEOUT, DEFAULT_ELO, K

def good_match(elo1: float, elo2: float, pct_t1: float, pct_t2: float) -> bool:
    """
    Determine if two players are a good match based on their Elo scores and queue times.

    Args:
        elo1 (float): Elo score of the first player.
        elo2 (float): Elo score of the second player.
        pct_t1 (float): Percentage of queue time passed for the first player.
        pct_t2 (float): Percentage of queue time passed for the second player.

    Returns:
        bool: True if players are a good match, False otherwise.
    """
    elo1_range = (elo1 - elo1 * (1 - pct_t1), elo1 + elo1 * (1 - pct_t1))
    elo2_range = (elo2 - elo2 * (1 - pct_t2), elo2 + elo2 * (1 - pct_t2))

    return (elo1_range[0] <= elo2 <= elo1_range[1]) or (elo2_range[0] <= elo1 <= elo2_range[1])

def match_players(player_tuples, num_players_required):
    """
    Attempts to create groups of players that match the required number of players.

    Args:
        player_tuples (List[Tuple[Matchmaking, float, float]]): List of players with their Elo and queue time percentage.
        num_players_required (int): Number of players required for a game.

    Returns:
        List[List[Matchmaking]]: List of matched player groups.
    """
    # Sort players by how long they've waited (percentage of timeout reached)
    player_tuples.sort(key=lambda x: x[2], reverse=True)
    
    # Try to form groups of the required size
    matched_groups = []
    used_players = set()  # To track players already matched
    
    # Generate all possible combinations of the required number of players
    for player_combination in combinations(player_tuples, num_players_required):
        all_match = True
        # Check if all players in the combination match with each other
        for i, player1 in enumerate(player_combination):
            for player2 in player_combination[i + 1:]:
                if not good_match(player1[1], player2[1], player1[2], player2[2]):
                    all_match = False
                    break
            if not all_match:
                break
        
        # If all players in this combination are a good match, add to matched groups
        if all_match:
            # Ensure no player is reused
            if not any(player in used_players for player in player_combination):
                matched_groups.append(player_combination)
                # Mark players as used
                for player in player_combination:
                    used_players.add(player)
    
    return matched_groups

def print_all_queues(all_players_with_elo: list):
    """
    Prints a comprehensive table of all models currently in the matchmaking queue across all environments.

    Args:
        all_players_with_elo (list): List of tuples containing matchmaking entries, Elo scores, and queue time percentages.
    """
    table_data = []
    for player, elo, pct_time in all_players_with_elo:
        time_in_queue = (time.time() - player.joined_at) / 60  # Convert to minutes
        queue_time_limit = player.time_limit / 60  # Convert to minutes
        table_data.append([
            player.model_name,
            player.environment_id,
            elo,
            f"{time_in_queue:.2f}",
            f"{queue_time_limit:.2f}"
        ])
    
    headers = ["Model Name", "Environment ID", "Elo Score", "Queue Time (min)", "Queue Time Limit (min)"]
    print("\nCurrent Queue for All Environments:")
    print(tabulate(table_data, headers=headers, tablefmt="pretty"))

def print_matched_groups(environment_id: str, matched_groups: list):
    """
    Prints tables of matched groups for a specific environment.

    Args:
        environment_id (str): The environment ID.
        matched_groups (list): List of matched player groups.
    """
    for idx, group in enumerate(matched_groups, start=1):
        table_data = []
        for player_tuple in group:
            player = player_tuple[0]
            elo = player_tuple[1]
            table_data.append([
                player.model_name,
                environment_id,
                elo
            ])
        
        headers = ["Model Name", "Environment ID", "Elo Score"]
        print(f"\nMatched Group {idx} in Environment '{environment_id}':")
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

def handle_step_timeouts(db: Session):
    """
    Checks for any player games where the player has not submitted a step within STEP_TIMEOUT seconds.

    Args:
        db (Session): Database session.
    """
    current_time = time.time()
    # Fetch all active games
    active_games = db.query(Game).filter(Game.status == "active").all()

    for game in active_games:
        for player_game in game.player_games:
            # Skip if player already has a reward (game might be already concluded)
            if player_game.reward is not None:
                continue

            # Check if it's the player's turn and if they've timed out
            # Assuming that last_action_time is set when it's the player's turn
            if player_game.last_action_time:
                time_since_last_action = current_time - player_game.last_action_time
                if time_since_last_action > STEP_TIMEOUT:
                    # Player has timed out
                    opponent_games = db.query(PlayerGame).filter(
                        PlayerGame.game_id == game.id,
                        PlayerGame.model_name != player_game.model_name,
                        PlayerGame.reward == None  # Only active players
                    ).all()

                    # Assign rewards
                    player_game.reward = -1  # Timed out player
                    for opp in opponent_games:
                        opp.reward = 0  # Neutral reward for opponents

                    # Update game status to finished
                    game.status = "finished"
                    game.reason = f"Player {player_game.player_id} timed out."

                    # calculate the updated elo for all players

                    # 1. extract all participating players, their previous elos, and whether they won
                    player_games = db.query(PlayerGame).filter(
                        PlayerGame.game_id == game.id
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
                            Elo.environment_id == game.environment_id
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
                    for model_name_pg, outcome, prev_elo in player_game_details:
                        opp_elos = [elo for mn, oc, elo in player_game_details if mn != model_name_pg]
                        if opp_elos:
                            opp_elo = sum(opp_elos) / len(opp_elos)
                        else:
                            opp_elo = DEFAULT_ELO  # Default if no opponents

                        # expected score for player
                        expected_outcome = 1 / (1 + 10**((opp_elo - prev_elo)/400))

                        updated_elo = prev_elo + K * (outcome - expected_outcome)
                        updated_elos.append(
                            (model_name_pg, updated_elo)
                        )

                    # Save updated Elo ratings to the database
                    for model_name_pg, elo in updated_elos:
                        new_elo_entry = Elo(
                            model_name=model_name_pg,
                            environment_id=game.environment_id,
                            elo=elo,
                            updated_at=time.time()
                        )
                        db.add(new_elo_entry)

                    db.commit()


                    print(f"Player {player_game.player_id} in Game {game.id} timed out. Game concluded.")
    return

def matchmaking_loop():
    """
    Continuously runs the matchmaking process, pairing players into games based on their Elo scores and queue times.
    """
    while True:
        # Initialize database connection
        db_gen = get_db()
        db: Session = next(db_gen, None)
        if not db:
            print("Failed to obtain database session.")
            time.sleep(5)
            continue

        current_time = time.time()
        
        try:
            # First, handle step timeouts
            handle_step_timeouts(db)

            # Fetch all environments
            environments = db.query(Environment).all()
            all_players_with_elo = []  # To accumulate all players across environments

            for environment in environments:
                num_players_required = environment.num_players
                environment_id = environment.environment_id
                
                # Fetch players in the matchmaking queue for this environment
                players_in_queue = (
                    db.query(Matchmaking)
                    .filter_by(environment_id=environment_id)
                    .order_by(Matchmaking.joined_at.asc())
                    .all()
                )

                # Remove players who haven't checked matchmaking status in N seconds
                inactive_players = []
                for player in players_in_queue:
                    time_since_last_checked = current_time - player.last_checked
                    if time_since_last_checked > MATCHMAKING_INACTIVITY_TIMEOUT:
                        inactive_players.append(player)

                for player in inactive_players:
                    db.delete(player)
                    db.commit()
                    print(f"Removed player '{player.model_name}' from matchmaking due to inactivity.")

                # Refresh players_in_queue after deletions
                players_in_queue = (
                    db.query(Matchmaking)
                    .filter_by(environment_id=environment_id)
                    .order_by(Matchmaking.joined_at.asc())
                    .all()
                )

                # Retrieve current Elo scores for each player (default to 1000 if not found)
                players_with_elo = []
                for player in players_in_queue:
                    elo_entry = (
                        db.query(Elo)
                        .filter_by(model_name=player.model_name, environment_id=environment_id)
                        .order_by(desc(Elo.updated_at))
                        .first()
                    )
                    elo_score = elo_entry.elo if elo_entry else 1000
                    pct_queue_time_passed = (current_time - player.joined_at) / player.time_limit
                    players_with_elo.append((player, elo_score, pct_queue_time_passed))
                    all_players_with_elo.append((player, elo_score, pct_queue_time_passed))
                
                # Attempt to match players only if enough are in the queue
                if len(players_with_elo) < num_players_required:
                    continue  # Not enough players to match
                
                # Attempt to match players
                matched_groups = match_players(
                    player_tuples=players_with_elo,
                    num_players_required=num_players_required
                )
                    
                if matched_groups:
                    # Pretty print the matched groups
                    print_matched_groups(environment_id, matched_groups)
                
                for player_group in matched_groups:
                    # Create a new game
                    new_game = Game(
                        environment_id=environment_id,
                        started_at=current_time,
                        status="active"  # Set initial game status
                    )
                    db.add(new_game)
                    db.commit()  # Commit to get the game ID
                    db.refresh(new_game)

                    # Initialize the environment for the new game
                    EnvironmentManager.get_env(game_id=new_game.id, env_id=environment_id)

                    # Add each player to PlayerGame and remove from Matchmaking
                    for i, player_tuple in enumerate(player_group):
                        player = player_tuple[0]
                        player_game_entry = PlayerGame(
                            game_id=new_game.id,
                            model_name=player.model_name,
                            player_id=i,  # Assign a unique player ID
                            last_action_time=time.time()  # Initialize as None
                        )
                        db.add(player_game_entry)
                        db.delete(player)  # Remove from matchmaking queue
                    
                    db.commit()  # Commit all changes at once
                
                # Handle players who have exceeded their queue time limit
                for player_tuple in players_with_elo:
                    player = player_tuple[0]
                    pct_time = player_tuple[2]
                    if pct_time >= 1.0:  # Queue time limit exceeded
                        standard_agent = "standard_agent"  # Replace with actual standard agent logic
                        new_game = Game(
                            environment_id=environment_id,
                            started_at=current_time,
                            status="active"
                        )
                        db.add(new_game)
                        db.commit()
                        db.refresh(new_game)
                        
                        # Initialize the environment for the new game
                        EnvironmentManager.get_env(game_id=new_game.id, env_id=environment_id)
                        
                        # Add the player and standard agent to PlayerGame
                        player_game_entry = PlayerGame(
                            game_id=new_game.id,
                            model_name=player.model_name,
                            player_id=1  # Assign a unique player ID
                        )
                        agent_game_entry = PlayerGame(
                            game_id=new_game.id,
                            model_name=standard_agent,
                            player_id=2  # Assign a unique ID for the standard agent
                        )
                        db.add(player_game_entry)
                        db.add(agent_game_entry)
                        db.delete(player)
                        
                        db.commit()
                        
                        # Log the creation of a game with a standard agent
                        print(f"\nPlayer '{player.model_name}' has exceeded the queue time limit and has been matched with a standard agent in Environment '{environment_id}'.")

            # After processing all environments, print the comprehensive queue table
            if all_players_with_elo:
                print_all_queues(all_players_with_elo)
            else:
                print("\nNo players currently in the matchmaking queues.")

        except Exception as e:
            print(f"Error in matchmaking loop: {e}")
        finally:
            db.close()
        
        # Sleep to avoid continuous polling
        time.sleep(5)  # Adjust as needed to control matchmaking frequency

if __name__ == "__main__":
    # Run the matchmaking loop in a separate thread to prevent blocking
    matchmaking_thread = threading.Thread(target=matchmaking_loop, daemon=True)
    matchmaking_thread.start()

    # Keep the main thread alive
    while True:
        time.sleep(60)
