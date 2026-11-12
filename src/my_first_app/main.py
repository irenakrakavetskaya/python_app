from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .database import create_db_and_tables, get_session
from .dependencies import get_token_header as verify_token
from .exceptions import (
    UnicornException,
    unicorn_exception_handler,
    validation_exception_handler,
)
from .internal import admin
from .routers import (
    auth,
    examples,
    forms_uploads,
    heroes,
    invoice,
    item_examples,
    items,
    streaming,
    users,
    websocket,
)
from .routers.heroes import Hero

__all__ = ["Hero", "app", "get_session", "verify_token"]

app = FastAPI()
app.include_router(users.router)
app.include_router(items.router)
app.include_router(websocket.router)
app.include_router(invoice.router)
app.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    responses={418: {"description": "I'm a teapot"}},
)

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


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


app.include_router(examples.info_router)
app.include_router(auth.token_router)
app.add_exception_handler(UnicornException, unicorn_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(examples.notification_router)
app.include_router(streaming.router)
app.include_router(item_examples.router)
app.include_router(examples.files_router)
app.include_router(item_examples.creation_router)
app.include_router(examples.weights_router)
app.include_router(auth.user_router)
app.include_router(examples.portal_router)
app.include_router(item_examples.name_router)
app.include_router(auth.fake_token_router)
app.include_router(forms_uploads.router)
app.include_router(auth.current_user_router)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = perf_counter()
    response = await call_next(request)
    process_time = perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


app.include_router(heroes.router)
