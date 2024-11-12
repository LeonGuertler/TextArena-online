# environment_manager.py
from typing import Dict
import textarena as ta  # Ensure textarena is properly installed and imported

class OnlineEnvHandler:
    """
    Handles the state and actions of an online game environment.
    """

    def __init__(self, env_id: str):
        self.env = ta.make(env_id)  # Initialize the environment using textarena
        self.observations = self.env.reset()
        self.done = False

    def check_done(self) -> bool:
        """
        Check if the game is done.

        Returns:
            bool: True if the game is done, False otherwise.
        """
        return self.done

    def check_player_turn(self, player_id: int) -> bool:
        """
        Check if it's the specified player's turn.

        Args:
            player_id (int): Player ID to check.

        Returns:
            bool: True if it's the player's turn, False otherwise.
        """
        return player_id == self.env.state.current_player

    def get_observation(self, player_id: int) -> Dict:
        """
        Get observations for the specified player.

        Args:
            player_id (int): Player ID.

        Returns:
            Dict: Observations for the player.
        """
        return {player_id: self.observations[player_id]}

    def execute_step(self, player_id: int, action: str):
        """
        Execute a player's action and update the game state.

        Args:
            player_id (int): Player ID.
            action (str): Action to execute.
        
        Returns:
            Tuple: Reward and info after executing the step.
        """
        if self.done:
            return 
        print(f"Player {player_id}: {action}")
        game_observations, self.reward, truncated, terminated, self.info = self.env.step(
            player_id=player_id, action=action
        )
        for pid in game_observations:
            self.observations[pid] = game_observations[pid]
        self.done = terminated or truncated

    def extract_results(self):
        """ TODO """
        return self.reward, self.info


class EnvironmentManager:
    """
    Manages all active game environments.
    """
    _environments: Dict[int, OnlineEnvHandler] = {}

    @classmethod
    def get_env(cls, game_id: int, env_id: str) -> OnlineEnvHandler:
        if game_id not in cls._environments:
            cls._environments[game_id] = OnlineEnvHandler(env_id)
        return cls._environments[game_id]

    @classmethod
    def remove_env(cls, game_id: int):
        if game_id in cls._environments:
            del cls._environments[game_id]
