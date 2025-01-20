import textarena as ta 
import threading
from typing import Optional, Dict, List , Tuple


# db imports
from database import get_db 
from sqlalchemy.orm import Session

# core imports
from core.models import Game, PlayerGame, PlayerLog

# import configs
from config import STANDARD_MODELS


class EnvironmentManagerBase:
    _instance = None
    _lock = threading.Lock()
    _environments: Dict = {}
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    @classmethod
    def get_env(cls, *args, **kwargs):
        raise NotImplementedError
        
    @classmethod
    def remove_env(cls, game_id: int):
        if game_id in cls._environments:
            del cls._environments[game_id]

    @staticmethod
    def determine_env_type(game_id: int, db: Session) -> str:
        """Determine whether to use local or online environment."""
        players = db.query(PlayerGame).filter(PlayerGame.game_id == game_id).all()
        return "local" if any(p.model_name in STANDARD_MODELS for p in players) else "online"
    
    @staticmethod
    def get_appropriate_manager(game_id: int, db: Session):
        """Get the appropriate environment manager based on game type."""
        env_type = EnvironmentManagerBase.determine_env_type(game_id, db)
        if env_type == "local":
            return LocalEnvironmentManager
        return OnlineEnvironmentManager


class OnlineEnvHandler:
    def __init__(self, env_id: str):
        self.env = ta.make(env_id)
        self.env.reset()
        self.done = False
        self.info = {}
        self.reward = {}
        self.env_id = self.env.env_id  # Store the specific env ID
        print("OnlineEnvHandler initialized:", self.env, self.env.env_id)

    def get_initial_observation(self, player_id):
        return self.initial_observations[player_id]

    def check_done(self) -> bool:
        return self.done

    def check_player_turn(self, player_id: int) -> bool:
        print("OnlineEnvHandler check:", self.env, self.env.env_id)
        return player_id == self.env.state.current_player_id

    def get_observation(self, player_id: int):
        pid, obs = self.env.get_observation()
        assert pid == player_id, "Unexpected Error. Players ids don't match in get_observation"
        return obs

    def execute_step(self, action: str):
        print(f'\n\nExecuting action: {action}\n\n')
        if self.done:
            return
        self.done, self.info = self.env.step(action=action)

    def extract_results(self):
        self.rewards = self.env.close()
        return self.rewards, self.info

class OnlineEnvironmentManager(EnvironmentManagerBase):
    @classmethod
    def get_env(cls, game_id: int, env_id: str, db: Session = None) -> OnlineEnvHandler:
        """Get or create environment for a game."""
        with cls._lock:
            if game_id not in cls._environments:
                cls._environments[game_id] = OnlineEnvHandler(env_id)
            return cls._environments[game_id]

class LocalEnvHandler:
    def __init__(self, env_id: str, local_model: str, local_pid: int, game_id: int):
        self.env = ta.make(env_id)
        self.env.reset()
        self.done = False
        self.info = {}
        self.reward = {}
        self.env_id = self.env.env_id  # Store the specific env ID
        self.local_model_name = local_model
        print("\nInitializing LocalEnvHandler for model:", self.local_model_name)
        self.local_model = ta.agents.OpenRouterAgent(model_name=local_model)
        self.local_pid = local_pid 
        self.local_obs = []
        self.game_id = game_id

        # If local model should move immediately:
        while self.env.state.current_player_id == self.local_pid and not self.done:
            self._execute_local_model_step()
            print(f"LocalEnvHandler stuck: current_player_id={self.env.state.current_player_id}, local_pid={self.local_pid}")
            time.sleep(1)

    def get_initial_observation(self, player_id):
        return self.initial_observations[player_id]
        
    def check_done(self) -> bool:
        return self.done

    def check_player_turn(self, player_id: int) -> bool:
        return player_id == self.env.state.current_player_id

    def get_observation(self, player_id: int):
        pid, obs = self.env.get_observation()
        assert pid == player_id, "Unexpected Error. Players ids don't match in get_observation"
        return obs

    def execute_step(self, action: str):
        print("LocalEnvHandler: Executing global model step.")

        # Update local model last action time
        db = next(get_db())
        try:
            pg = db.query(PlayerGame).join(Game).filter(
                PlayerGame.model_name == self.local_model_name,
                Game.id == self.game_id
            ).first()
            pg.last_action_time = time.time()
            db.commit()
        finally:
            db.close()

        if self.done:
            return

        self.done, self.info = self.env.step(action=action)

        while self.local_pid == self.env.state.current_player_id and not self.done:
            self._execute_local_model_step()
            time.sleep(1)

    def extract_results(self):
        self.rewards = self.env.close()
        return self.rewards, self.info

    def _execute_local_model_step(self):
        print("LocalEnvHandler: Executing local step")
        if self.done:
            return
        obs_timestamp = time.time()
        _, obs_json = self.env.get_observation()
        obs = self._transform_local_obs(obs=obs_json)
        action = self.local_model(obs)
        action_timestamp = time.time()

        # Log the action
        db = next(get_db())
        try:
            pg = db.query(PlayerGame).join(Game).filter(
                PlayerGame.model_name == self.local_model_name,
                Game.id == self.game_id
            ).first()

            log_entry = PlayerLog(
                player_game_id=pg.id,
                model_name=self.local_model_name,
                observation=json.dumps(obs_json),
                timestamp_observation=obs_timestamp,
                timestamp_action=action_timestamp,
                action=action
            )
            db.add(log_entry)
            db.commit()

            # Update player's last action time
            pg.last_action_time = time.time()
            db.commit()
        finally:
            db.close()

        self.done, self.info = self.env.step(action=action)
        print("LocalEnvHandler: Local step executed")
        print(f"Current player: {self.env.state.current_player_id}, Local Model ID: {self.local_pid}")

    def _transform_local_obs(self, obs: Optional[List[Tuple[int, str]]]):
        if obs is not None:
            self.local_obs.extend(obs)

        if not self.local_obs:
            return "No observation."

        str_observation = ""
        for sender_id, message in self.local_obs:
            sender_name = "GAME" if sender_id == ta.GAME_ID else self.env.state.role_mapping.get(sender_id, f"Player {sender_id}")
            str_observation += f"\n[{sender_name}] {message}"
        return str_observation

class LocalEnvironmentManager(EnvironmentManagerBase):
    @classmethod
    def get_env(cls, game_id: int, env_id: str, db: Session = None) -> LocalEnvHandler:
        """Get or create environment for a game."""
        with cls._lock:
            if game_id not in cls._environments:
                # Initialize if needed
                players = db.query(PlayerGame).filter(PlayerGame.game_id == game_id).all()
                standard_player = next(p for p in players if p.model_name in STANDARD_MODELS)
                cls._environments[game_id] = LocalEnvHandler(
                    env_id=env_id,
                    local_model=standard_player.model_name,
                    local_pid=standard_player.player_id,
                    game_id=game_id
                )
            return cls._environments[game_id]