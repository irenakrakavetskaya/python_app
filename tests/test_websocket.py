from fastapi.testclient import TestClient

from my_first_app.main import app

client = TestClient(app)


def test_websocket_page():
    response = client.get("/websocket")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>WebSocket Chat</h1>" in response.text


def test_websocket():
    with client, client.websocket_connect("/ws/1") as first:
        with client.websocket_connect("/ws/2") as second:
            first.send_text("Hello WebSocket")
            assert first.receive_text() == "You wrote: Hello WebSocket"
            assert first.receive_text() == "Client #1 says: Hello WebSocket"
            assert second.receive_text() == "Client #1 says: Hello WebSocket"

        assert first.receive_text() == "Client #2 left the chat"
