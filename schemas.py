# schemas.py
from pydantic import BaseModel, EmailStr
from fastapi import Depends, Query
from typing import Optional, Dict, Any


class ModelRegistrationRequest(BaseModel):
    """
    Schema for model registration requests.
    """
    model_name: str 
    description: str 
    email: EmailStr


class MatchmakingRegistrationRequest(BaseModel):
    """
    Schema for joining matchmaking requests.
    """
    env_id: str 
    model_name: str 
    model_token: str 
    queue_time_limit: Optional[float] = 300


# Commented out classes remain as they are if not used.

class StepRequest(BaseModel):
    """
    Schema for submitting a step/action.
    """
    env_id: str 
    model_name: str 
    model_token: str 
    game_id: int 
    action_text: str


class GetResultsRequest(BaseModel):
    """ TODO """
    game_id: int
    model_name: str 
    env_id: str 


