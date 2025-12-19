from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from src.schemas.models import UserInDB, UserSchema
from src.config import get_db
from src.utils.auth_utils import verify_token
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> UserInDB:
    payload = verify_token(token)
    if payload is None or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload["sub"]
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


class UserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None


@router.get("/users/{user_id}", response_model=UserSchema)
async def get_user_by_id(user_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload["sub"]
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this profile")
    return user


@router.put("/{user_id}", response_model=UserSchema)
async def update_profile(
    user_id: int,
    update: UserUpdate,
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user),
):
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    if update.name is not None:
        user.name = update.name
    if update.password is not None:
        from src.utils.auth_utils import hash_password

        user.hashed_password = hash_password(update.password)
    db.commit()
    db.refresh(user)
    return user 


@router.post("/complete-onboarding", response_model=UserSchema)
async def complete_onboarding(
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user),
):
    """Mark user's onboarding as completed."""
    if user.onboarding_completed:
        # Already completed, just return the user
        return user
    
    user.onboarding_completed = True
    from datetime import timezone
    user.onboarding_completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


class PushTokenRequest(BaseModel):
    push_token: str
    device_type: str = "expo"  # expo, ios, android


@router.post("/push-token")
async def register_push_token(
    token_data: PushTokenRequest,
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user),
):
    """Register or update user's push notification token."""
    user.push_token = token_data.push_token
    user.device_type = token_data.device_type
    db.commit()
    return {"detail": "Push token registered successfully"}


@router.delete("/push-token")
async def remove_push_token(
    db: Session = Depends(get_db),
    user: UserInDB = Depends(get_current_user),
):
    """Remove user's push notification token."""
    user.push_token = None
    user.device_type = None
    db.commit()
    return {"detail": "Push token removed successfully"}
