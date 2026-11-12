from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from fastapi.responses import JSONResponse, RedirectResponse

from .. import config

info_router = APIRouter()
notification_router = APIRouter()
files_router = APIRouter()
weights_router = APIRouter()
portal_router = APIRouter()


@lru_cache
def get_settings():
    return config.Settings()


@info_router.get("/info")
async def info(settings: Annotated[config.Settings, Depends(get_settings)]):
    return {
        "app_name": settings.app_name,
        "admin_email": settings.admin_email,
        "items_per_user": settings.items_per_user,
    }


@notification_router.get("/")
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


@notification_router.post("/send-notification/{email}")
async def send_notification(
    email: str, background_tasks: BackgroundTasks, q: Annotated[str, Depends(get_query)]
):
    message = f"message to {email}\n"
    background_tasks.add_task(write_log, message)
    return {"message": "Message sent"}


@files_router.get("/files/{file_path:path}")
async def read_file(file_path: str):
    return {"file_path": file_path}


@weights_router.post("/index-weights/")
async def create_index_weights(weights: dict[int, float]):
    return weights


@portal_router.get("/portal", response_model=None)
async def get_portal(teleport: bool = False) -> Response:
    if teleport:
        return RedirectResponse(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    return JSONResponse(content={"message": "Here's your interdimensional portal."})
