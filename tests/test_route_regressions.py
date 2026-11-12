import warnings

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from my_first_app import database
from my_first_app.dependencies import get_token_header
from my_first_app.main import app, verify_token
from my_first_app.routers import item_examples


def test_existing_route_precedence():
    client = TestClient(app)
    assert client.get("/").json() == {"Hello": "World"}
    assert client.get("/items/plumbus").json() == {
        "name": "Plumbus",
        "item_id": "plumbus",
    }
    assert client.get("/items/stream").status_code == 404
    assert client.get("/users/").json() == [
        {"username": "Rick"},
        {"username": "Morty"},
    ]
    assert client.get("/users/me/").status_code == 401
    assert (
        client.post("/token", data={"username": "unknown", "password": "x"}).status_code
        == 401
    )
    response = client.post(
        "/uploadfile/", files=[("files", ("one.txt", b"data", "text/plain"))]
    )
    assert response.json() == {"filenames": ["one.txt"]}


def test_openapi_still_describes_later_duplicate_routes():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        paths = app.openapi()["paths"]
    assert paths["/"]["get"]["operationId"] == "main__get"
    assert paths["/token"]["post"]["operationId"] == "login_token_post"
    assert (
        paths["/uploadfile/"]["post"]["operationId"] == "upload_file_uploadfile__post"
    )


def test_validation_and_streaming():
    client = TestClient(app)
    invalid = client.post("/items/", json={})
    assert invalid.status_code == 400
    assert "Field: ('body', 'name')" in invalid.text

    streamed = client.post("/chat/stream", json={"text": "hello world"})
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert streamed.text == (
        'event: token\ndata: "hello"\n\n'
        'event: token\ndata: "world"\n\n'
        "event: done\ndata: [DONE]\n\n"
    )


def test_shared_token_dependency_override():
    assert verify_token is get_token_header
    isolated_app = FastAPI()
    isolated_app.include_router(item_examples.router)
    calls = []

    def override_token():
        calls.append(True)

    isolated_app.dependency_overrides[verify_token] = override_token
    response = TestClient(isolated_app).get(
        "/items/?size=1",
        headers={"X-Key": "fake-super-secret-key", "Authorization": "Bearer token"},
    )
    assert response.status_code == 422
    assert calls == [True]


def test_startup_creates_hero_table(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(database, "engine", engine)
    try:
        with TestClient(app):
            assert inspect(engine).has_table("hero")
    finally:
        engine.dispose()
