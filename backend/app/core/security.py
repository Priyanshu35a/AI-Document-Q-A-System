import hashlib
import secrets
import logging
from typing import Optional, Tuple
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, UserSession

logger = logging.getLogger(__name__)

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with a unique salt.
    Zero external C-dependency friction, cryptographically secure.
    """
    if salt is None:
        salt = secrets.token_hex(16)
    
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex(), salt

def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """Verifies a password against the stored hash and salt."""
    key, _ = hash_password(password, salt)
    return secrets.compare_digest(key, hashed_password)

def generate_session_token() -> str:
    """Generates a secure random 64-character hex session token."""
    return secrets.token_hex(32)

from fastapi import Depends, HTTPException, Header, Query, status

def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None, description="Session token for direct download links"),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency to authenticate current user from either:
    1. Authorization header: 'Bearer <token>'
    2. Query parameter: '?token=<token>' (for file/CSV downloads)
    """
    extracted_token = None

    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            extracted_token = parts[1]
        elif len(parts) == 1:
            extracted_token = parts[0]
    elif token and token.strip():
        extracted_token = token.strip()

    if not extracted_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_record = db.query(UserSession).filter(UserSession.token == extracted_token).first()
    if not session_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == session_record.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_optional_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Optional user dependency that returns None instead of raising if unauthenticated."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization, db)
    except HTTPException:
        return None
