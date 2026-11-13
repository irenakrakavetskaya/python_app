import random
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path as FilePath
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import AfterValidator, BaseModel, Field, HttpUrl
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from ..database import SessionDep
from ..models import (
    ImageCreate,
    ImagePublic,
    Item,
    ItemCreate,
    ItemImage,
    ItemPublic,
    ItemTagLink,
    ItemUpdate,
    Tag,
    TagPublic,
)
from .auth import CurrentUser, get_current_active_user

# =====================================================================
# Real items API (PostgreSQL)
# =====================================================================
router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

tags_router = APIRouter(
    prefix="/tags",
    tags=["tags"],
    dependencies=[Depends(get_current_active_user)],
)


def get_item_or_404(item_id: int, session: SessionDep) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


ItemDep = Annotated[Item, Depends(get_item_or_404)]


def get_own_item(item: ItemDep, current_user: CurrentUser) -> Item:
    if item.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your item")
    return item


OwnItemDep = Annotated[Item, Depends(get_own_item)]


def get_or_create_tags(session: Session, names: list[str]) -> list[Tag]:
    tags = []
    for name in dict.fromkeys(names):  # drop duplicates, keep order
        tag = session.exec(select(Tag).where(Tag.name == name)).first()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
        tags.append(tag)
    return tags


@router.get("/", response_model=list[ItemPublic])
def read_items(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
    tag: str | None = None,
):
    # selectinload fetches images/tags in 2 extra queries total, not 2 per item
    query = select(Item).options(selectinload(Item.images), selectinload(Item.tags))
    if tag:
        query = (
            query.join(ItemTagLink, ItemTagLink.item_id == Item.id)
            .join(Tag, Tag.id == ItemTagLink.tag_id)
            .where(Tag.name == tag.strip().lower())
        )
    return session.exec(query.order_by(Item.id).offset(offset).limit(limit)).all()


@router.post("/", response_model=ItemPublic, status_code=201)
def create_item(item_in: ItemCreate, session: SessionDep, current_user: CurrentUser):
    item = Item.model_validate(
        item_in.model_dump(exclude={"tags", "images"}),
        update={"owner_id": current_user.id},
    )
    item.tags = get_or_create_tags(session, item_in.tags)
    item.images = [ItemImage(url=str(img.url), name=img.name) for img in item_in.images]
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/{item_id}", response_model=ItemPublic)
def read_item(item: ItemDep):
    return item


@router.patch(
    "/{item_id}",
    response_model=ItemPublic,
    responses={403: {"description": "Not the owner"}},
)
def update_item(item: OwnItemDep, item_in: ItemUpdate, session: SessionDep):
    data = item_in.model_dump(exclude_unset=True)
    tag_names = data.pop("tags", None)
    item.sqlmodel_update(data)
    if tag_names is not None:  # [] clears all tags, omitted/null leaves them alone
        item.tags = get_or_create_tags(session, tag_names)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete(
    "/{item_id}",
    status_code=204,
    responses={403: {"description": "Not the owner"}},
)
def delete_item(item: OwnItemDep, session: SessionDep):
    session.delete(item)  # images and tag links are removed with it
    session.commit()


@router.post(
    "/{item_id}/images",
    response_model=ImagePublic,
    status_code=201,
    responses={403: {"description": "Not the owner"}},
)
def add_image(item: OwnItemDep, image_in: ImageCreate, session: SessionDep):
    image = ItemImage(item_id=item.id, url=str(image_in.url), name=image_in.name)
    session.add(image)
    session.commit()
    session.refresh(image)
    return image


@router.delete(
    "/{item_id}/images/{image_id}",
    status_code=204,
    responses={403: {"description": "Not the owner"}},
)
def delete_image(item: OwnItemDep, image_id: int, session: SessionDep):
    image = session.get(ItemImage, image_id)
    if image is None or image.item_id != item.id:
        raise HTTPException(status_code=404, detail="Image not found")
    session.delete(image)
    session.commit()


@tags_router.get("/", response_model=list[TagPublic])
def read_tags(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    return session.exec(
        select(Tag).order_by(Tag.name).offset(offset).limit(limit)
    ).all()


# =====================================================================
# Tutorial demos (no database) - safe to delete once you no longer need them
# =====================================================================
demo_router = APIRouter(
    tags=["demo"],
    dependencies=[Depends(get_current_active_user)],
)

data = {
    "isbn-9781529046137": "The Hitchhiker's Guide to the Galaxy",
    "imdb-tt0371724": "The Hitchhiker's Guide to the Galaxy",
    "isbn-9781439512982": "Isaac Asimov: The Complete Stories, Vol. 2",
}

# Resolve relative to this file, not the working directory
templates = Jinja2Templates(
    directory=FilePath(__file__).resolve().parent.parent / "templates"
)


class Image(BaseModel):
    url: HttpUrl
    name: str


class ModelName(str, Enum):
    alexnet = "alexnet"
    resnet = "resnet"
    lenet = "lenet"


class Pagination(BaseModel):
    limit: int = Field(10, ge=1)
    offset: int = Field(0, ge=0)


class Filters(BaseModel):
    order_by: Literal["created_at", "updated_at"] = "created_at"
    tags: list[str] = []


class DateRange(BaseModel):
    start: date
    end: date


class Cookies(BaseModel):
    model_config = {"extra": "forbid"}
    session_id: str
    fatebook_tracker: str | None = None
    googall_tracker: str | None = None


class CommonHeaders(BaseModel):
    host: str
    save_data: bool
    if_modified_since: str | None = None
    traceparent: str | None = None
    x_tag: list[str] = []


def check_valid_id(id: str):
    if not id.startswith(("isbn-", "imdb-")):
        raise ValueError('Invalid ID format, it must start with "isbn-" or "imdb-"')
    return id


@demo_router.get("/filtered-items/")
async def read_filtered_items(
    pagination: Annotated[Pagination, Query()],
    filters: Annotated[Filters, Query()],
    search: str | None = None,
    date_range: Annotated[DateRange | None, Query()] = None,
):
    return {"pagination": pagination, "filters": filters, "search": search}


@demo_router.get("/books/")
async def read_books(
    cookies: Annotated[Cookies, Cookie()],
    headers: Annotated[CommonHeaders, Header()],
    id: Annotated[str | None, AfterValidator(check_valid_id)] = None,
):
    if id:
        item = data.get(id)
    else:
        id, item = random.choice(list(data.items()))
    return {"id": id, "name": item}


@demo_router.get("/items-template/{id}", response_class=HTMLResponse)
async def read_template(request: Request, id: str):
    return templates.TemplateResponse(
        request=request, name="item_path.html", context={"id": id}
    )


@demo_router.put("/new-items/{item_id}")
async def read_new_items(
    item_id: UUID,
    start_datetime: Annotated[datetime, Body()],
    end_datetime: Annotated[datetime, Body()],
    process_after: Annotated[timedelta, Body()],
    repeat_at: Annotated[time | None, Body()] = None,
):
    start_process = start_datetime + process_after
    duration = end_datetime - start_process
    return {
        "item_id": item_id,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "process_after": process_after,
        "repeat_at": repeat_at,
        "start_process": start_process,
        "duration": duration,
    }


@demo_router.get("/models/{model_name}")
async def get_model(model_name: ModelName):
    if model_name is ModelName.alexnet:
        return {"model_name": model_name, "message": "Deep Learning FTW!"}

    if model_name.value == "lenet":
        return {"model_name": model_name, "message": "LeCNN all the images"}

    return {"model_name": model_name, "message": "Have some residuals"}


@demo_router.post("/images/multiple/")
async def create_multiple_images(images: list[Image]):
    return images
