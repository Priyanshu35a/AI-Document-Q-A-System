import re
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, UserSession
from app.core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    get_current_user
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email format.")
        return v

class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email or Username")
    password: str = Field(..., min_length=1)

class UserResponse(BaseModel):
    id: int
    username: str
    email: str

class AuthResponse(BaseModel):
    token: str
    user: UserResponse

@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    """Register a new user account and generate an authenticated session token."""
    username = req.username.strip().lower()
    email = req.email.strip().lower()

    # Check for existing username
    existing_username = db.query(User).filter(User.username == username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already taken. Please choose another."
        )

    # Check for existing email
    existing_email = db.query(User).filter(User.email == email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists."
        )

    # Hash password & create user
    hashed_pw, salt = hash_password(req.password)
    user = User(
        username=username,
        email=email,
        hashed_password=hashed_pw,
        salt=salt
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create session token
    token = generate_session_token()
    session = UserSession(token=token, user_id=user.id)
    db.add(session)
    db.commit()

    logger.info(f"New user registered: {username} ({email}) - User ID: {user.id}")

    return AuthResponse(
        token=token,
        user=UserResponse(id=user.id, username=user.username, email=user.email)
    )

@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Log in an existing user with email/username and password."""
    ident = req.identifier.strip().lower()
    user = db.query(User).filter(
        (User.email == ident) | (User.username == ident)
    ).first()

    if not user or not verify_password(req.password, user.hashed_password, user.salt):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your username/email and password."
        )

    # Generate session token
    token = generate_session_token()
    session = UserSession(token=token, user_id=user.id)
    db.add(session)
    db.commit()

    logger.info(f"User logged in: {user.username} - User ID: {user.id}")

    return AuthResponse(
        token=token,
        user=UserResponse(id=user.id, username=user.username, email=user.email)
    )

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Retrieve profile of the currently authenticated user."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email
    )

@router.post("/logout")
def logout(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Invalidate current user session."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        db.query(UserSession).filter(UserSession.token == token).delete()
        db.commit()
    return {"status": "success", "message": "Successfully logged out."}
