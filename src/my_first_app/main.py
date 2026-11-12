import random
from collections.abc import AsyncIterable
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from functools import lru_cache
from time import perf_counter
from typing import Annotated, Any, Literal
from uuid import UUID

import jwt
from fastapi import (
    BackgroundTasks,
    Body,
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.templating import Jinja2Templates
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import AfterValidator, BaseModel, EmailStr, Field, HttpUrl
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, create_engine, select

from . import config

# from .dependencies import get_query_token, get_token_header
from .internal import admin
from .routers import invoice, items, users, websocket

# app = FastAPI(dependencies=[Depends(get_query_token)])
app = FastAPI()
app.include_router(users.router)
app.include_router(items.router)
app.include_router(websocket.router)
app.include_router(invoice.router)
app.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    # dependencies=[Depends(get_token_header)],
    responses={418: {"description": "I'm a teapot"}},
)

# openssl rand -hex 32
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")

data = {
    "isbn-9781529046137": "The Hitchhiker's Guide to the Galaxy",
    "imdb-tt0371724": "The Hitchhiker's Guide to the Galaxy",
    "isbn-9781439512982": "Isaac Asimov: The Complete Stories, Vol. 2",
}

items = {
    "foo": {"name": "Foo", "price": 50.2},
    "bar": {"name": "Bar", "description": "The Bar fighters", "price": 62, "tax": 20.2},
}


fake_users_db = {
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": "fakehashedsecret",
        "disabled": False,
    },
    "alice": {
        "username": "alice",
        "full_name": "Alice Wonderson",
        "email": "alice@example.com",
        "hashed_password": "fakehashedsecret2",
        "disabled": True,
    },
}

origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

sqlite_file_name = "database.db"
# create the database later
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


class StreamItem(BaseModel):
    name: str
    description: str | None


streamItems = [
    StreamItem(name="Plumbus", description="A multi-purpose household device."),
    StreamItem(name="Portal Gun", description="A portal opening device."),
    StreamItem(name="Meeseeks Box", description="A box that summons a Meeseeks."),
]


class Prompt(BaseModel):
    text: str


class HeroBase(SQLModel):
    name: str = SQLField(index=True)
    age: int | None = SQLField(default=None, index=True)


class Hero(HeroBase, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    secret_name: str


class HeroPublic(HeroBase):
    id: int


class HeroCreate(HeroBase):
    secret_name: str


class HeroUpdate(HeroBase):
    name: str | None = None
    age: int | None = None
    secret_name: str | None = None


class FormData(BaseModel):
    username: str
    password: str
    model_config = {"extra": "forbid"}


class Profile(BaseModel):
    name: str
    age: int


class Preferences(BaseModel):
    tags: list[str] = []


class Image(BaseModel):
    url: HttpUrl
    name: str


class Person(BaseModel):
    kind: Literal["person"]
    name: str


class Company(BaseModel):
    kind: Literal["company"]
    company_name: str


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


class User(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: str | None = None


class UserIn(UserBase):
    password: str


class UserOut(UserBase):
    pass


class UserInDB(User):
    hashed_password: str


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


class UnicornException(Exception):
    def __init__(self, name: str):
        self.name = name


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def check_valid_id(id: str):
    if not id.startswith(("isbn-", "imdb-")):
        raise ValueError('Invalid ID format, it must start with "isbn-" or "imdb-"')
    return id


def fake_password_hasher(raw_password: str):
    return "supersecret" + raw_password


def fake_save_user(user_in: UserIn):
    hashed_password = fake_password_hasher(user_in.password)
    user_in_db = UserInDB(**user_in.model_dump(), hashed_password=hashed_password)
    print("User saved! ..not really")
    return user_in_db


async def verify_token(x_token: Annotated[str, Header()]):
    if x_token != "fake-super-secret-token":
        raise HTTPException(status_code=400, detail="X-Token header invalid")


async def verify_key(x_key: Annotated[str, Header()]):
    if x_key != "fake-super-secret-key":
        raise HTTPException(status_code=400, detail="X-Key header invalid")
    return x_key


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        verify_password(password, DUMMY_HASH)
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def fake_decode_token(token):
    # This doesn't provide any security at all
    user = get_user(fake_users_db, token)
    return user


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@lru_cache
def get_settings():
    return config.Settings()


@app.get("/info")
async def info(settings: Annotated[config.Settings, Depends(get_settings)]):
    return {
        "app_name": settings.app_name,
        "admin_email": settings.admin_email,
        "items_per_user": settings.items_per_user,
    }


@app.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


def fake_hash_password(password: str):
    return "fakehashed" + password


async def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}


CommonsDep = Annotated[dict, Depends(common_parameters)]


@app.exception_handler(UnicornException)
async def unicorn_exception_handler(request: Request, exc: UnicornException):
    return JSONResponse(
        status_code=418,
        content={"message": f"Oops! {exc.name} did something. There goes a rainbow..."},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    message = "Validation errors:"
    for error in exc.errors():
        message += f"\nField: {error['loc']}, Error: {error['msg']}, Body: {exc.body}"
    return PlainTextResponse(message, status_code=400)


@app.get("/")
def read_root():
    return {"Hello": "World"}


def write_notification(email: str, message=""):
    with open("log.txt", mode="w") as email_file:
        content = f"notification for {email}: {message}"
        email_file.write(content)


def write_log(message: str):
    with open("log.txt", mode="a") as log:
        log.write(message)


def get_query(background_tasks: BackgroundTasks, q: str | None = None):
    if q:
        message = f"found query: {q}\n"
        background_tasks.add_task(write_log, message)
    return q


@app.post("/send-notification/{email}")
async def send_notification(
    email: str, background_tasks: BackgroundTasks, q: Annotated[str, Depends(get_query)]
):
    message = f"message to {email}\n"
    background_tasks.add_task(write_log, message)
    return {"message": "Message sent"}


@app.get("/items/stream", response_class=EventSourceResponse)
async def sse_items() -> AsyncIterable[StreamItem]:
    for item in StreamItem:
        yield item


@app.get("/items/stream-retry", response_class=EventSourceResponse)
async def stream_items() -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(comment="stream of item updates")
    for i, item in enumerate(streamItems):
        yield ServerSentEvent(data=item, event="item_update", id=str(i + 1), retry=5000)


@app.post("/chat/stream", response_class=EventSourceResponse)
async def stream_chat(prompt: Prompt) -> AsyncIterable[ServerSentEvent]:
    words = prompt.text.split()
    for word in words:
        yield ServerSentEvent(data=word, event="token")
    yield ServerSentEvent(raw_data="[DONE]", event="done")


@app.get("/filtered-items/", tags=["items"])
async def read_filtered_items(
    pagination: Annotated[Pagination, Query()],
    filters: Annotated[Filters, Query()],
    search: str | None = None,
    date_range: Annotated[DateRange | None, Query()] = None,
):
    return {"pagination": pagination, "filters": filters, "search": search}


@app.get("/books/", tags=["items"])
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


@app.get("/items-template/{id}", response_class=HTMLResponse)
async def read_template(request: Request, id: str):
    return templates.TemplateResponse(
        request=request, name="item_path.html", context={"id": id}
    )


@app.get(
    "/items/", dependencies=[Depends(verify_token), Depends(verify_key)], tags=["items"]
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


@app.get(
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


@app.put("/items/{item_id}", tags=["items"])
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


@app.patch("/items/{item_id}")
async def patch_item(item_id: str, item: Item) -> Item:
    stored_item_data = items[item_id]
    stored_item_model = Item(**stored_item_data)
    update_data = item.model_dump(exclude_unset=True)
    updated_item = stored_item_model.model_copy(update=update_data)
    items[item_id] = jsonable_encoder(updated_item)
    return updated_item


@app.put("/new-items/{item_id}", tags=["items"])
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


@app.get("/models/{model_name}")
async def get_model(model_name: ModelName):
    if model_name is ModelName.alexnet:
        return {"model_name": model_name, "message": "Deep Learning FTW!"}

    if model_name.value == "lenet":
        return {"model_name": model_name, "message": "LeCNN all the images"}

    return {"model_name": model_name, "message": "Have some residuals"}


@app.get("/files/{file_path:path}")
async def read_file(file_path: str):
    return {"file_path": file_path}


@app.post(
    "/items/", response_model=Item, status_code=status.HTTP_201_CREATED, tags=["items"]
)
async def create_item(item: Item) -> Any:
    return item


@app.post("/images/multiple/")
async def create_multiple_images(images: list[Image]):
    return images


@app.post("/index-weights/")
async def create_index_weights(weights: dict[int, float]):
    return weights


@app.post("/user/", response_model=UserOut, tags=["users"])
async def create_user(user_in: UserIn):
    user_saved = fake_save_user(user_in)
    return user_saved


@app.get("/users/", tags=["users"])
async def read_users(commons: CommonsDep):
    return commons


@app.get("/portal", response_model=None)
async def get_portal(teleport: bool = False) -> Response:
    if teleport:
        return RedirectResponse(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    return JSONResponse(content={"message": "Here's your interdimensional portal."})


@app.get(
    "/items/{item_id}/name",
    response_model=Item,
    response_model_include={"name", "description"},
    tags=["items"],
)
async def read_item_name(item_id: str):
    return items[item_id]


@app.post("/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user_dict = fake_users_db.get(form_data.username)
    if not user_dict:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    user = UserInDB(**user_dict)
    hashed_password = fake_hash_password(form_data.password)
    if not hashed_password == user.hashed_password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    return {"access_token": user.username, "token_type": "bearer"}


@app.post("/preferences/")
async def update_preferences(subscribe: Annotated[bool, Form()] = False):
    return {"subscribe": subscribe}


@app.post("/profiles/")
async def create_profile(
    preferences: Annotated[Preferences, Form()],
    token: Annotated[str, Form()],
    profile: Annotated[Profile | None, Form()] = None,
):
    return {"profile": profile, "preferences": preferences, "token": token}


@app.post("/contacts/")
async def create_contact(
    contact: Annotated[Person | Company | None, Form(discriminator="kind")] = None,
):
    return contact


@app.post("/files/")
async def create_file(
    files: Annotated[
        list[bytes] | None, File(description="Multiple files as bytes")
    ] = None,
):
    if not files:
        return {"message": "No file sent"}
    else:
        return {"file_sizes": [len(file) for file in files]}


@app.post("/uploadfile/")
async def create_upload_file(
    files: Annotated[
        list[UploadFile], File(description="Multiple files as UploadFile")
    ],
):
    return {"filenames": [file.filename for file in files]}


@app.post("/uploadfile/")
async def upload_file(
    file: Annotated[bytes, File()],
    fileb: Annotated[UploadFile, File()],
    token: Annotated[str, Form()],
):
    return {
        "file_size": len(file),
        "token": token,
        "fileb_content_type": fileb.content_type,
    }


@app.get("/")
async def main():
    content = """
<body>
<form action="/files/" enctype="multipart/form-data" method="post">
<input name="files" type="file" multiple>
<input type="submit">
</form>
<form action="/uploadfiles/" enctype="multipart/form-data" method="post">
<input name="files" type="file" multiple>
<input type="submit">
</form>
</body>
    """
    return HTMLResponse(content=content)


@app.get("/users/me/")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user


@app.get("/users/me/items/")
async def read_own_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return [{"item_id": "Foo", "owner": current_user.username}]


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = perf_counter()
    response = await call_next(request)
    process_time = perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.post("/heroes/", response_model=HeroPublic)
def create_hero(hero: HeroCreate, session: SessionDep):
    db_hero = Hero.model_validate(hero)
    session.add(db_hero)
    session.commit()
    session.refresh(db_hero)
    return db_hero


@app.get("/heroes/", response_model=list[HeroPublic])
def read_heroes(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    heroes = session.exec(select(Hero).offset(offset).limit(limit)).all()
    return heroes


@app.get("/heroes/{hero_id}", response_model=HeroPublic)
def read_hero(hero_id: int, session: SessionDep):
    hero = session.get(Hero, hero_id)
    if not hero:
        raise HTTPException(status_code=404, detail="Hero not found")
    return hero


@app.patch("/heroes/{hero_id}", response_model=HeroPublic)
def update_hero(hero_id: int, hero: HeroUpdate, session: SessionDep):
    hero_db = session.get(Hero, hero_id)
    if not hero_db:
        raise HTTPException(status_code=404, detail="Hero not found")
    hero_data = hero.model_dump(exclude_unset=True)
    hero_db.sqlmodel_update(hero_data)
    session.add(hero_db)
    session.commit()
    session.refresh(hero_db)
    return hero_db


@app.delete("/heroes/{hero_id}")
def delete_hero(hero_id: int, session: SessionDep):
    hero = session.get(Hero, hero_id)
    if not hero:
        raise HTTPException(status_code=404, detail="Hero not found")
    session.delete(hero)
    session.commit()
    return {"ok": True}
