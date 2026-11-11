from importlib import import_module

from fastapi.testclient import TestClient

main = import_module("my_first_app.main")


def test_process_time_header(monkeypatch):
    readings = iter([10.0, 10.25])
    monkeypatch.setattr(main, "perf_counter", lambda: next(readings))

    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert response.headers["X-Process-Time"] == "0.25"


def test_datetime_time_request():
    response = TestClient(main.app).put(
        "/new-items/00000000-0000-0000-0000-000000000001",
        json={
            "start_datetime": "2024-01-01T10:00:00",
            "end_datetime": "2024-01-01T11:00:00",
            "process_after": 60,
            "repeat_at": "12:34:56",
        },
    )

    assert response.status_code == 200
    assert response.json()["repeat_at"] == "12:34:56"
    assert float(response.headers["X-Process-Time"]) >= 0
