from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .auth import get_current_active_user

router = APIRouter(
    tags=["profile"],
    dependencies=[Depends(get_current_active_user)],  # every route needs login
)


class FormData(BaseModel):
    username: str
    password: str
    model_config = {"extra": "forbid"}


class Profile(BaseModel):
    name: str
    age: int


class Preferences(BaseModel):
    tags: list[str] = []


class Person(BaseModel):
    kind: Literal["person"]
    name: str


class Company(BaseModel):
    kind: Literal["company"]
    company_name: str


@router.post("/preferences/")
async def update_preferences(subscribe: Annotated[bool, Form()] = False):
    return {"subscribe": subscribe}


@router.post("/profiles/")
async def create_profile(
    preferences: Annotated[Preferences, Form()],
    token: Annotated[str, Form()],
    profile: Annotated[Profile | None, Form()] = None,
):
    return {"profile": profile, "preferences": preferences, "token": token}


@router.post("/contacts/")
async def create_contact(
    contact: Annotated[Person | Company | None, Form(discriminator="kind")] = None,
):
    return contact


@router.post("/files/")
async def create_file(
    files: Annotated[
        list[bytes] | None, File(description="Multiple files as bytes")
    ] = None,
):
    if not files:
        return {"message": "No file sent"}
    else:
        return {"file_sizes": [len(file) for file in files]}


@router.post("/uploadfile/")
async def create_upload_file(
    files: Annotated[
        list[UploadFile], File(description="Multiple files as UploadFile")
    ],
):
    return {"filenames": [file.filename for file in files]}


@router.post("/uploadfile/")
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


@router.get("/")
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
