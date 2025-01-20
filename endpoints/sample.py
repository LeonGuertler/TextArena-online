# endpoints/model_endpoints.py
from fastapi import APIRouter, Depends, HTTPException, Request
import secrets, time
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Model
from core.schemas import ModelRegistrationRequest
from config import RATE_LIMIT
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.post("/register_model")
@limiter.limit(f"{RATE_LIMIT}/minute")
def register_model(request: Request, payload: ModelRegistrationRequest, db: Session = Depends(get_db)):
    existing = db.query(Model).filter(Model.model_name == payload.model_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Model name exists.")
    model_token = secrets.token_hex(16)
    new_model = Model(
        model_name=payload.model_name,
        description=payload.description,
        email=payload.email,
        model_token=model_token
    )
    db.add(new_model)
    db.commit()
    return {"model_token": model_token}
