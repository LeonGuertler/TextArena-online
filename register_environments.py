import textarena as ta 
from database import get_db 
from models import Environment
import sys

def register_env(env_id: str, num_players: int):
    """
    Register a new environment with a unique ID and the required number of players.

    Args:
        env_id (str): Unique identifier for the environment.
        num_players (int): Number of players required for the environment.
    """
    # Initialize database session using the context manager approach
    db = next(get_db())
    try:
        # Check if environment_id is unique
        existing_environment = db.query(Environment).filter(Environment.environment_id == env_id).first()
        if existing_environment:
            print(f"Environment ID '{env_id}' already exists.")
            return

        # Create and add new Environment instance
        new_environment = Environment(
            environment_id=env_id,
            num_players=num_players
        )
        db.add(new_environment)
        db.commit()
        db.refresh(new_environment)

        # Confirm successful registration
        print(f"Environment registered successfully: {new_environment.environment_id}")

    except Exception as e:
        print(f"Error registering environment '{env_id}': {e}")
    finally:
        # Close the session to free up resources
        db.close()


def register_envs():
    register_env(
        env_id="DontSayIt-v0",
        num_players=2
    )

    register_env(
        env_id="TruthAndDeception-v0",
        num_players=2
    )

    register_env(
        env_id="Negotiation-v0",
        num_players=2
    )

if __name__ == "__main__":
    # Example: Register a specific environment
    register_env(
        env_id="DontSayIt-v0",
        num_players=2
    )

    register_env(
        env_id="TruthAndDeception-v0",
        num_players=2
    )
