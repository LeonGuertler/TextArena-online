from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from database import Base

class Model(Base):
    __tablename__ = "models"
    model_name = Column(String, primary_key=True)
    description = Column(Text)
    email = Column(String)
    model_token = Column(String, unique=True, nullable=False)
    matchmakings = relationship("Matchmaking", back_populates="model")
    player_games = relationship("PlayerGame", back_populates="model")
    elos = relationship("Elo", back_populates="model")
    logs = relationship("PlayerLog", back_populates="model")

class Elo(Base):
    __tablename__ = "elos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)
    environment_id = Column(String, ForeignKey("environments.environment_id"), nullable=False)
    elo = Column(Float, nullable=False, default=1000)
    updated_at = Column(Float, nullable=False)
    model = relationship("Model", back_populates="elos")
    environment = relationship("Environment")

class Environment(Base):
    __tablename__ = "environments"
    environment_id = Column(String, primary_key=True)
    num_players = Column(Integer, nullable=False)
    matchmakings = relationship("Matchmaking", back_populates="environment")
    games = relationship("Game", back_populates="environment")

class Matchmaking(Base):
    __tablename__ = "matchmakings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    environment_id = Column(String, ForeignKey("environments.environment_id"), nullable=False)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)
    human_ip = Column(String, ForeignKey("human_players.ip_address"), nullable=True)
    is_human = Column(Boolean, default=False)
    joined_at = Column(Float, nullable=False)
    time_limit = Column(Float, nullable=False, default=300)
    last_checked = Column(Float, nullable=False)
    model = relationship("Model", back_populates="matchmakings")
    environment = relationship("Environment", back_populates="matchmakings")

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, autoincrement=True)
    environment_id = Column(String, ForeignKey("environments.environment_id"), nullable=False)
    specific_env_id = Column(String, nullable=True)  # Store the specific env ID
    started_at = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    environment = relationship("Environment", back_populates="games")
    player_games = relationship("PlayerGame", back_populates="game")


class PlayerGame(Base):
    __tablename__ = "player_games"
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)
    player_id = Column(Integer, nullable=False)
    reward = Column(Integer, nullable=True)
    outcome = Column(String, nullable=True)
    last_action_time = Column(Float, nullable=True)
    is_human = Column(Boolean, default=False)
    human_ip = Column(String, nullable=True)  # Store IP for human players
    game = relationship("Game", back_populates="player_games")
    model = relationship("Model", back_populates="player_games")
    logs = relationship("PlayerLog", back_populates="player_game")

class PlayerLog(Base):
    __tablename__ = "player_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_game_id = Column(Integer, ForeignKey("player_games.id"), nullable=False)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)
    timestamp_observation = Column(Float, nullable=False)
    observation = Column(Text, nullable=False)
    timestamp_action = Column(Float, nullable=True)
    action = Column(Text, nullable=True)
    player_game = relationship("PlayerGame", back_populates="logs")
    model = relationship("Model", back_populates="logs")



class HumanPlayer(Base):
    __tablename__ = "human_players"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String, nullable=False)
    games_played = Column(Integer, default=0)
    created_at = Column(Float, nullable=False)
    last_active = Column(Float, nullable=False)