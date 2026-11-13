import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.server import app as server_app
from app.server.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_landing_page_and_built_static_index(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, "STATIC", str(tmp_path / "no_static"))
    c = TestClient(create_app())
    assert "python-app-template" in c.get("/").text
    assert "Say hello" in c.get("/").text
    assert c.get("/api/health").json()["ok"] is True

    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<h1>built react app</h1>", encoding="utf8")
    (static / "assets" / "main.js").write_text("console.log(1)", encoding="utf8")
    monkeypatch.setattr(server_app, "STATIC", str(static))
    c2 = TestClient(create_app())
    assert c2.get("/").text == '<base href="./"><h1>built react app</h1>'
    assert "console.log(1)" in c2.get("/assets/main.js").text


def test_every_page_path_serves_the_app_with_a_base_back_to_its_root(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html><head><title>t</title></head></html>", encoding="utf8")
    (static / "favicon.svg").write_text("<svg/>", encoding="utf8")
    monkeypatch.setattr(server_app, "STATIC", str(static))
    c = TestClient(create_app())
    assert c.get("/settings?tab=appearance").text == '<html><head><base href="./"><title>t</title></head></html>'
    assert '<base href="../">' in c.get("/log/2026").text  # one level down: one step back up
    assert c.get("/favicon.svg").text == "<svg/>"
    for escape in (
        "..%5Capp.py",
        "..%2Fapp.py",
        "C:%5Cwindows%5Cwin.ini",
        "..",
    ):  # never a file outside the static folder: the app instead
        assert c.get("/" + escape).text.startswith("<html><head><base")
    assert c.get("/api/nope").status_code == 404  # an unknown endpoint is not the app
    assert c.get("/api/nope").json() == {"detail": "no such endpoint"}


def test_system_paging_and_removing_one_greeting(client):
    for n in ("a", "b", "c"):
        client.post("/api/messages", json={"name": n})
    s = client.get("/api/system").json()
    assert s["messages"] == 3
    assert s["disk"]["total"] > 0
    assert s["data_bytes"] > 0
    page = client.get("/api/messages/page", params={"limit": 2}).json()
    assert [m["name"] for m in page["messages"]] == ["c", "b"]
    assert page["has_more"] is True
    assert client.get("/api/messages/page", params={"after": 2, "limit": 2}).json() == {
        "messages": [client.get("/api/messages").json()[2]],
        "has_more": False,
    }
    assert client.get("/api/messages/page", params={"limit": 0}).status_code == 422
    assert client.delete("/api/messages/2").json()["name"] == "b"
    assert client.delete("/api/messages/2").status_code == 404
    assert [m["name"] for m in client.get("/api/messages").json()] == ["c", "a"]


def test_hello_and_messages_lifecycle(client):
    assert client.get("/api/hello").json() == {"name": "World", "greeting": "Hello", "message": "Hello, World!"}
    assert client.get("/api/hello", params={"name": "Ada", "greeting": "Hi"}).json()["message"] == "Hi, Ada!"
    assert client.get("/api/hello", params={"name": "x" * 121}).status_code == 400

    assert client.get("/api/messages").json() == []
    m = client.post("/api/messages", json={"name": "Ada", "greeting": "Hi"}).json()
    assert m["id"] == 1
    assert m["message"] == "Hi, Ada!"
    assert client.post("/api/messages", json={"name": "x" * 121}).status_code == 400
    assert len(client.get("/api/messages").json()) == 1
    assert client.delete("/api/messages").json() == {"cleared": 1}
    assert client.get("/api/messages").json() == []


def test_settings_roundtrip_and_server_main(client, tmp_path, monkeypatch):
    assert client.put("/api/settings", json={"data_dir": "relative/path"}).status_code == 400
    new_dir = str(tmp_path / "custom_data")
    monkeypatch.delenv("APP_DATA", raising=False)
    res = client.put("/api/settings", json={"data_dir": new_dir, "greeting": "Hey"}).json()
    assert res == {"data_dir": new_dir, "greeting": "Hey"}
    assert client.get("/api/settings").json() == {"data_dir": new_dir, "greeting": "Hey"}

    runs = []
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port, log_level: runs.append((host, port, log_level)))
    server_app.main(["--host", "127.0.0.1", "--port", "8360"])
    assert runs == [("127.0.0.1", 8360, "warning")]


def test_settings_put_with_one_field_or_none_changes_only_what_was_sent(client, tmp_path, monkeypatch):
    monkeypatch.delenv("APP_DATA", raising=False)
    new_dir = str(tmp_path / "data")
    assert client.put("/api/settings", json={"data_dir": new_dir}).json()["data_dir"] == new_dir
    assert client.put("/api/settings", json={"greeting": "Hey"}).json() == {"data_dir": new_dir, "greeting": "Hey"}
    assert client.put("/api/settings", json={}).json() == {"data_dir": new_dir, "greeting": "Hey"}
