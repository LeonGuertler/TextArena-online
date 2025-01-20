
# FastAPI imports
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# SlowAPI imports
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# db imports
from database import engine, get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, case, label, and_

# # core imports
from core.models import (Base)
# from core.models import (
#     Model, Base, Environment, Matchmaking, PlayerGame, 
#     Game, Elo, PlayerLog, HumanPlayer
# )
# from core.schemas import (
#     ModelRegistrationRequest, MatchmakingRegistrationRequest,
#     LeaveMatchmakingRequest, StepRequest, GetResultsRequest,
#     HumanMoveRequest
# )

# utility imports
from typing import Tuple
import secrets, time, json
from collections import defaultdict
# from urllib.parse import unquote

# config imports
# from config import (
#     DATABASE_URL, DEFAULT_ELO, MATCHMAKING_INACTIVITY_TIMEOUT, 
#     STEP_TIMEOUT, RATE_LIMIT, STANDARD_MODELS, HUMANITY_MODEL_NAME,
#     ENV_NAME_TO_ID, REVERSE_GAME_ID_MAP
# )


# import env handlers
from env_handlers import (
    EnvironmentManagerBase,
    OnlineEnvHandler,
    LocalEnvHandler
)

# import utils
# from app_utils import (
#     categorize_reason
# )


# import endpoints
from endpoints import model_play, human_play, analytics, website

# local imports
import register_environments

# Initialize FastAPI
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://textarena.ai"], 
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"], 
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# include endpoints
app.include_router(model_play.router)
app.include_router(human_play.router)
app.include_router(analytics.router)
app.include_router(website.router)

# Mount the uploads directory as static files so that images are accessible via URL.
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Initialize Limiter
limiter = Limiter(key_func=get_remote_address)

# remaining setup
Base.metadata.create_all(bind=engine)
register_environments.register_envs()
db = next(get_db())
try:
    register_environments.register_standard_models(db=db)
finally:
    db.close()

# rate limit handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


@app.on_event("shutdown")
async def shutdown_event():
    pass 

    