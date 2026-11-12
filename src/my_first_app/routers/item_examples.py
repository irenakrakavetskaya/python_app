import random
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import AfterValidator, BaseModel, Field, HttpUrl

from ..dependencies import get_token_header
from .auth import UserIn, oauth2_scheme

router = APIRouter()
creation_router = APIRouter()
name_router = APIRouter()

data = {
    "isbn-9781529046137": "The Hitchhiker's Guide to the Galaxy",
    "imdb-tt0371724": "The Hitchhiker's Guide to the Galaxy",
    "isbn-9781439512982": "Isaac Asimov: The Complete Stories, Vol. 2",
}

items = {
    "foo": {"name": "Foo", "price": 50.2},
    "bar": {"name": "Bar", "description": "The Bar fighters", "price": 62, "tax": 20.2},
}

templates = Jinja2Templates(directory="templates")


class Image(BaseModel):
    url: HttpUrl
    name: str


class Item(BaseModel):
    name: str = Field(examples=["Foo"])
    price: float = Field(gt=0, description="The price must be greater than zero")
    description: str | None = Field(
        default=None, title="The description of the item", max_length=300
    )
    is_offer: bool | None = None
    tax: float | None = None
    tags: set[str] = set()
    images: list[Image] | None = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Foo",
                    "description": "A very nice Item",
                    "price": 35.4,
                    "tax": 3.2,
                    "tags": ["rock", "metal", "bar"],
                    "images": [
                        {
                            "url": "https://example.com/image.png",
                            "name": "Example Image",
                        }
                    ],
                }
            ]
        }
    }


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


async def verify_key(x_key: Annotated[str, Header()]):
    if x_key != "fake-super-secret-key":
        raise HTTPException(status_code=400, detail="X-Key header invalid")
    return x_key


@router.get("/filtered-items/", tags=["items"])
async def read_filtered_items(
    pagination: Annotated[Pagination, Query()],
    filters: Annotated[Filters, Query()],
    search: str | None = None,
    date_range: Annotated[DateRange | None, Query()] = None,
):
    return {"pagination": pagination, "filters": filters, "search": search}


@router.get("/books/", tags=["items"])
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


@router.get("/items-template/{id}", response_class=HTMLResponse)
async def read_template(request: Request, id: str):
    return templates.TemplateResponse(
        request=request, name="item_path.html", context={"id": id}
    )


@router.get(
    "/items/",
    dependencies=[Depends(get_token_header), Depends(verify_key)],
    tags=["items"],
)
async def read_items(
    item_id: Annotated[int, Path(title="The ID of the item to get", ge=1, le=1000)],
    token: Annotated[str, Depends(oauth2_scheme)],
    size: Annotated[float, Query(gt=0, lt=10.5)],
    q: Annotated[
        str | None,
        Query(
            title="Query string",
            description="Query string for the items to search in the database that have a good match",
            alias="item-query",
            min_length=3,
            max_length=50,
            pattern="^fixedquery$",
        ),
    ] = None,
) -> list[Item]:
    results = {"item_id": item_id}
    if q:
        results.update({"q": q})
    if size:
        results.update({"size": size})
    return results


@router.get(
    "/items/{item_id}",
    response_model=Item,
    response_model_exclude_unset=True,
    tags=["items"],
)
async def read_item(item_id: str, q: str | None = None, short: bool = False):
    item = {"item_id": item_id}
    if item_id not in items:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
            headers={"X-Error": "There goes my error"},
        )
    if item_id == 3:
        raise HTTPException(status_code=418, detail="Nope! I don't like 3.")
    if q:
        item.update({"q": q})
    if not short:
        item.update(
            {"description": "This is an amazing item that has a long description"}
        )
    return item


@router.put("/items/{item_id}", tags=["items"])
async def update_item(
    *,
    item_id: int,
    item: Item,
    user: UserIn,
    importance: Annotated[int, Body(gt=0)],
    q: str | None = None,
):
    json_compatible_item_data = jsonable_encoder(item)
    results = {
        "item_id": item_id,
        "item": json_compatible_item_data,
        "user": user,
        "importance": importance,
    }
    if q:
        results.update({"q": q})
    return results


@router.patch("/items/{item_id}")
async def patch_item(item_id: str, item: Item) -> Item:
    stored_item_data = items[item_id]
    stored_item_model = Item(**stored_item_data)
    update_data = item.model_dump(exclude_unset=True)
    updated_item = stored_item_model.model_copy(update=update_data)
    items[item_id] = jsonable_encoder(updated_item)
    return updated_item


@router.put("/new-items/{item_id}", tags=["items"])
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


@router.get("/models/{model_name}")
async def get_model(model_name: ModelName):
    if model_name is ModelName.alexnet:
        return {"model_name": model_name, "message": "Deep Learning FTW!"}

    if model_name.value == "lenet":
        return {"model_name": model_name, "message": "LeCNN all the images"}

    return {"model_name": model_name, "message": "Have some residuals"}


@creation_router.post(
    "/items/", response_model=Item, status_code=status.HTTP_201_CREATED, tags=["items"]
)
async def create_item(item: Item) -> Any:
    return item


@creation_router.post("/images/multiple/")
async def create_multiple_images(images: list[Image]):
    return images


@name_router.get(
    "/items/{item_id}/name",
    response_model=Item,
    response_model_include={"name", "description"},
    tags=["items"],
)
async def read_item_name(item_id: str):
    return items[item_id]
