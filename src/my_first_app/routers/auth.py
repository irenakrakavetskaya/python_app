import hashlib
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select, update

from ..database import SessionDep
from ..models import RefreshRequest, RefreshToken, Token, User, UserCreate, UserPublic
from ..ratelimit import limiter

SECRET_KEY = os.environ["SECRET_KEY"]  # required: app won't start without it
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 14

router = APIRouter(tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")


# ---------- users / passwords ----------
def get_user_by_username(session: Session, username: str) -> User | None:
    return session.exec(select(User).where(User.username == username)).first()


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(session, username)
    if not user:
        # Same work as a real check, so response time doesn't reveal valid usernames
        password_hash.verify(password, DUMMY_HASH)
        return None
    if not password_hash.verify(password, user.hashed_password):
        return None
    return user


# ---------- access tokens (short-lived JWT) ----------
def create_access_token(username: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError:
        raise credentials_exception from None
    username = payload.get("sub")
    if username is None:
        raise credentials_exception
    user = get_user_by_username(session, username)
    if user is None:
        raise credentials_exception
    return user


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_active_user)]


def get_current_admin(current_user: CurrentUser) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


AdminUser = Annotated[User, Depends(get_current_admin)]


# ---------- refresh tokens (random, stored hashed, rotated on every use) ----------
def hash_token(token: str) -> str:
    # SHA-256 is enough here: the token is long and random, unlike a password
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(
    session: Session, user: User, family_id: str | None = None
) -> str:
    """Adds a new refresh token to the session and returns the raw value.
    The caller commits, so issuing and revoking happen in one transaction."""
    raw = secrets.token_urlsafe(32)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            family_id=family_id or str(uuid.uuid4()),
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return raw


def revoke_family(session: Session, family_id: str) -> None:
    session.exec(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            col(RefreshToken.revoked_at).is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )


# ---------- endpoints ----------
@router.post("/auth/register", response_model=UserPublic, status_code=201)
@limiter.limit("10/hour")
def register(request: Request, user_in: UserCreate, session: SessionDep):
    user = User(
        username=user_in.username,
        email=user_in.email.lower(),
        full_name=user_in.full_name,
        hashed_password=password_hash.hash(user_in.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:  # unique constraint on username or email
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Username or email already registered"
        ) from None
    session.refresh(user)
    return user


@router.post("/token")
@limiter.limit("10/minute")
def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> Token:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    refresh = issue_refresh_token(session, user)  # new login = new family
    session.commit()
    return Token(
        access_token=create_access_token(user.username),
        refresh_token=refresh,
        token_type="bearer",
    )


@router.post("/auth/refresh")
@limiter.limit("30/minute")
def refresh_access_token(
    request: Request, body: RefreshRequest, session: SessionDep
) -> Token:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # FOR UPDATE locks the row, so two simultaneous requests can't both use one token
    stored = session.exec(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(body.refresh_token))
        .with_for_update()
    ).first()
    if stored is None:
        raise invalid

    if stored.revoked_at is not None:
        # An already-used token came back: assume it was stolen, kill the whole family
        revoke_family(session, stored.family_id)
        session.commit()
        raise invalid

    if stored.expires_at <= datetime.now(UTC):
        raise invalid

    user = session.get(User, stored.user_id)
    if user is None or user.disabled:
        raise invalid

    # Rotate: the old token dies, a new one continues the same family
    stored.revoked_at = datetime.now(UTC)
    session.add(stored)
    new_refresh = issue_refresh_token(session, user, family_id=stored.family_id)
    session.commit()
    return Token(
        access_token=create_access_token(user.username),
        refresh_token=new_refresh,
        token_type="bearer",
    )


@router.post("/auth/logout", status_code=204)
def logout(body: RefreshRequest, session: SessionDep):
    """Ends this login session. Always 204, so it doesn't reveal which tokens exist."""
    stored = session.exec(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(body.refresh_token)
        )
    ).first()
    if stored is not None:
        revoke_family(session, stored.family_id)
        session.commit()


@router.post("/auth/logout-all", status_code=204)
def logout_all(current_user: CurrentUser, session: SessionDep):
    """Ends every login session of the current user (all devices)."""
    session.exec(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == current_user.id,
            col(RefreshToken.revoked_at).is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    session.commit()
