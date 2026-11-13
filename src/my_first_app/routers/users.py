from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from ..database import SessionDep
from ..models import User, UserPublic
from .auth import CurrentUser, get_current_active_user

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(get_current_active_user)],  # every route needs login
)


@router.get("/", response_model=list[UserPublic])
def read_users(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    return session.exec(
        select(User).order_by(User.id).offset(offset).limit(limit)
    ).all()


# Must stay above "/{username}", or "me" would be treated as a username
@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser):
    return current_user


@router.get("/{username}", response_model=UserPublic)
def read_user(username: str, session: SessionDep):
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
