from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from ..database import SessionDep
from ..models import User, UserAdminUpdate, UserDetail, UserPublic
from .auth import AdminUser, CurrentUser, get_current_active_user, get_current_admin

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(get_current_active_user)],  # every route needs login
)

admin_router = APIRouter(
    prefix="/admin/users",
    tags=["admin"],
    dependencies=[Depends(get_current_admin)],  # every route needs admin
    responses={403: {"description": "Admin privileges required"}},
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
@router.get("/me", response_model=UserDetail)
def read_user_me(current_user: CurrentUser):
    return current_user


@router.get("/{username}", response_model=UserPublic)
def read_user(username: str, session: SessionDep):
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ---------- admin only ----------
@admin_router.get("/", response_model=list[UserDetail])
def admin_read_users(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    return session.exec(
        select(User).order_by(User.id).offset(offset).limit(limit)
    ).all()


@admin_router.patch("/{user_id}", response_model=UserDetail)
def admin_update_user(
    user_id: int, update: UserAdminUpdate, session: SessionDep, admin: AdminUser
):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = update.model_dump(exclude_unset=True, exclude_none=True)
    # An admin can't lock themselves out, so at least one admin always remains
    if user.id == admin.id and (
        changes.get("is_admin") is False or changes.get("disabled") is True
    ):
        raise HTTPException(
            status_code=400,
            detail="You can't remove your own admin rights or disable yourself",
        )

    user.sqlmodel_update(changes)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
