from sqlalchemy import (
    Column, String, Integer, Float, 
    ForeignKey, Text, DateTime, func, Text
)
from sqlalchemy.orm import relationship, declarative_base
from database import Base


class Model(Base):
    __tablename__ = "models"

    model_name = Column(String, primary_key=True)
    description = Column(Text)
    email = Column(String)
    model_token = Column(String, unique=True, nullable=False)

    # Relationships
    matchmakings = relationship("Matchmaking", back_populates="model")
    player_games = relationship("PlayerGame", back_populates="model")
    elos = relationship("Elo", back_populates="model")
    logs = relationship("PlayerLog", back_populates="model")  # Updated relationship


class Elo(Base):
    __tablename__ = "elos"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)
    environment_id = Column(String, ForeignKey("environments.environment_id"), nullable=False)
    elo = Column(Float, nullable=False, default=1000)
    updated_at = Column(Float, nullable=False)

    # Relationships
    model = relationship("Model", back_populates="elos")
    environment = relationship("Environment")


class Environment(Base):
    __tablename__ = "environments"

    environment_id = Column(String, primary_key=True)
    num_players = Column(Integer, nullable=False)

    # Relationships
    matchmakings = relationship("Matchmaking", back_populates="environment")
    games = relationship("Game", back_populates="environment")


class Matchmaking(Base):
    __tablename__ = "matchmakings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    environment_id = Column(String, ForeignKey("environments.environment_id"), nullable=False)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)
    joined_at = Column(Float, nullable=False)
    time_limit = Column(Float, nullable=False, default=300)
    last_checked = Column(Float, nullable=False, default=func.time())  # New column

    # Relationships
    model = relationship("Model", back_populates="matchmakings")
    environment = relationship("Environment", back_populates="matchmakings")


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    environment_id = Column(String, ForeignKey("environments.environment_id"), nullable=False)
    started_at = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    # Add other game-specific fields as needed
    reason = Column(Text, nullable=True)

    # Relationships
    environment = relationship("Environment", back_populates="games")
    player_games = relationship("PlayerGame", back_populates="game")


class PlayerGame(Base):
    __tablename__ = "player_games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)
    player_id = Column(Integer, nullable=False)
    reward = Column(Integer, nullable=True)
    last_action_time = Column(Float, nullable=True)  # New column to track step timeouts

    # Relationships
    game = relationship("Game", back_populates="player_games")
    model = relationship("Model", back_populates="player_games")
    logs = relationship("PlayerLog", back_populates="player_game")


class PlayerLog(Base):
    __tablename__ = "player_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_game_id = Column(Integer, ForeignKey("player_games.id"), nullable=False)
    model_name = Column(String, ForeignKey("models.model_name"), nullable=False)  # New foreign key
    timestamp_observation = Column(Float, nullable=False)
    observation = Column(Text, nullable=False)
    timestamp_action = Column(Float, nullable=True)
    action = Column(Text, nullable=True)

    # Relationships
    player_game = relationship("PlayerGame", back_populates="logs")
    model = relationship("Model", back_populates="logs")  # Updated relationship
