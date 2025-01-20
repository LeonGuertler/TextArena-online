from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional

class ModelRegistrationRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    model_name: str
    description: str
    email: EmailStr

class MatchmakingRegistrationRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    env_id: str
    model_name: str
    model_token: str
    queue_time_limit: Optional[float] = 300

class LeaveMatchmakingRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    model_name: str
    model_token: str
    env_id: str

class StepRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    env_id: str
    model_name: str
    model_token: str
    game_id: int
    action_text: str

class GetResultsRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    game_id: int
    model_name: str
    env_id: str

class HumanMoveRequest(BaseModel):
    game_id: int
    move: str