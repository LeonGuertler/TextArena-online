import textarena as ta
from database import get_db
from sqlalchemy.orm import Session
import secrets, time
from core.models import Model, Base, Environment, Matchmaking, PlayerGame, Game, Elo, PlayerLog

from config import STANDARD_MODELS, DEFAULT_ELO, HUMANITY_MODEL_NAME

def register_env(env_id: str, num_players: int):
    db = next(get_db())
    try:
        existing = db.query(Environment).filter(Environment.environment_id == env_id).first()
        if existing:
            return
        new_env = Environment(environment_id=env_id, num_players=num_players)
        db.add(new_env)
        db.commit()
    finally:
        db.close()

def register_envs():
    register_env("BalancedSubset-v0", 2)


# Also register standard models
def register_standard_models(db: Session):
    """Register standard models directly without using the online API"""
    for model_name in STANDARD_MODELS:
        existing = db.query(Model).filter(Model.model_name == model_name).first()
        if not existing:
            model_token = secrets.token_hex(16)
            new_model = Model(
                model_name=model_name,
                description=f"Official {model_name} model",
                email="system@textarena.ai",
                model_token=model_token
            )
            db.add(new_model)
            
            # Add initial Elo rating
            elo = Elo(
                model_name=model_name,
                environment_id="BalancedSubset-v0",
                elo=DEFAULT_ELO,
                updated_at=time.time()
            )
            db.add(elo)
    
    # Register humanity collective
    humanity = db.query(Model).filter(Model.model_name == HUMANITY_MODEL_NAME).first()
    if not humanity:
        model_token = secrets.token_hex(16)
        humanity = Model(
            model_name=HUMANITY_MODEL_NAME,
            description="Collective human players",
            email="system@textarena.ai",
            model_token=model_token
        )
        db.add(humanity)
        
        # Add initial Elo rating for humanity
        elo = Elo(
            model_name=HUMANITY_MODEL_NAME,
            environment_id="BalancedSubset-v0",
            elo=DEFAULT_ELO,
            updated_at=time.time()
        )
        db.add(elo)
    
    db.commit()