from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import EmailStr, HttpUrl, StringConstraints
from sqlalchemy import DateTime, false, func
from sqlmodel import Field, Relationship, SQLModel

# Tag names are trimmed and lower-cased on input: "Rock " and "rock" are the same tag
TagName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, min_length=1, max_length=50
    ),
]


# ---------- users ----------
class User(SQLModel, table=True):
    __tablename__ = "users"  # "user" is a reserved word in Postgres

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    full_name: str | None = None
    hashed_password: str
    disabled: bool = False
    is_admin: bool = Field(default=False, sa_column_kwargs={"server_default": false()})
    token_version: int = Field(default=0, sa_column_kwargs={"server_default": "0"})


class UserCreate(SQLModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    full_name: str | None = None
    password: str = Field(min_length=8, max_length=128)


class UserPublic(SQLModel):
    id: int
    username: str
    email: str
    full_name: str | None = None


class UserDetail(UserPublic):
    is_admin: bool
    disabled: bool


class UserAdminUpdate(SQLModel):
    is_admin: bool | None = None
    disabled: bool | None = None


class Token(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str


# ---------- items, tags, images ----------
class ItemBase(SQLModel):
    name: str = Field(min_length=1, max_length=100, index=True)
    description: str | None = Field(default=None, max_length=300)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    tax: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    is_offer: bool = False


class ItemTagLink(SQLModel, table=True):
    """Many-to-many link: one row per (item, tag) pair."""

    __tablename__ = "item_tags"

    item_id: int = Field(foreign_key="items.id", primary_key=True, ondelete="CASCADE")
    tag_id: int = Field(foreign_key="tags.id", primary_key=True, ondelete="CASCADE")


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=50, index=True, unique=True)

    items: list[Item] = Relationship(back_populates="tags", link_model=ItemTagLink)


class ItemImage(SQLModel, table=True):
    __tablename__ = "item_images"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True, ondelete="CASCADE")
    url: str = Field(max_length=2048)
    name: str = Field(max_length=100)

    item: Item = Relationship(back_populates="images")


class Item(ItemBase, table=True):
    __tablename__ = "items"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
        nullable=False,
    )

    images: list[ItemImage] = Relationship(back_populates="item", cascade_delete=True)
    tags: list[Tag] = Relationship(back_populates="items", link_model=ItemTagLink)


class ImageCreate(SQLModel):
    url: HttpUrl
    name: str = Field(min_length=1, max_length=100)


class ImagePublic(SQLModel):
    id: int
    url: str
    name: str


class TagPublic(SQLModel):
    id: int
    name: str


class ItemCreate(ItemBase):
    tags: list[TagName] = Field(default_factory=list, max_length=20)
    images: list[ImageCreate] = Field(default_factory=list, max_length=10)


class ItemUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    tax: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    is_offer: bool | None = None
    tags: list[TagName] | None = Field(default=None, max_length=20)  # replaces all tags


class ItemPublic(ItemBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    images: list[ImagePublic] = []
    tags: list[TagPublic] = []


class RefreshRequest(SQLModel):
    refresh_token: str = Field(min_length=1, max_length=200)


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    token_hash: str = Field(
        max_length=64, index=True, unique=True
    )  # SHA-256, never the raw token
    family_id: str = Field(
        max_length=36, index=True
    )  # all tokens from one login share this
    expires_at: datetime = Field(sa_type=DateTime(timezone=True), index=True)
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
