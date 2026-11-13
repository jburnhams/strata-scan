"""The HTTP API over real on-disk files: health check, greetings, message log, and settings."""


def test_health_and_hello_endpoints(client):
    assert client.get("/api/health").json() == {"ok": True, "version": "0.1.0"}
    assert client.get("/api/hello", params={"name": "Linus"}).json() == {
        "name": "Linus",
        "greeting": "Hello",
        "message": "Hello, Linus!",
    }


def test_messages_created_via_http_persist_and_can_be_cleared(client, cli):
    assert client.get("/api/messages").json() == []
    m1 = client.post("/api/messages", json={"name": "Alice"}).json()
    m2 = client.post("/api/messages", json={"name": "Bob", "greeting": "Hi"}).json()
    assert m1["id"] == 1
    assert m2["id"] == 2
    assert [m["message"] for m in client.get("/api/messages").json()] == ["Hi, Bob!", "Hello, Alice!"]
    assert "Hi, Bob!" in cli("messages").stdout
    assert client.delete("/api/messages").json() == {"cleared": 2}
    assert client.get("/api/messages").json() == []


def test_settings_changes_affect_subsequent_greetings(client):
    assert client.put("/api/settings", json={"greeting": "Bonjour"}).json()["greeting"] == "Bonjour"
    assert client.get("/api/hello", params={"name": "Monde"}).json()["message"] == "Bonjour, Monde!"
    assert client.put("/api/settings", json={"data_dir": "relative"}).status_code == 400


def test_one_greeting_removed_over_http_is_gone_from_the_cli_and_the_log(client, cli):
    for n in ("Ann", "Ben", "Cat"):
        client.post("/api/messages", json={"name": n})
    assert client.delete("/api/messages/2").status_code == 200
    out = cli("messages").stdout
    assert "Hello, Ben!" not in out
    assert "Hello, Ann!" in out
    assert "Hello, Cat!" in out
    assert client.post("/api/messages", json={"name": "Dee"}).json()["id"] == 4
    page = client.get("/api/messages/page", params={"limit": 2}).json()
    assert [m["name"] for m in page["messages"]] == ["Dee", "Cat"]
    assert page["has_more"] is True
    assert client.get("/api/system").json()["messages"] == 3


def test_a_reload_on_any_screen_gets_the_app(client):
    r = client.get("/settings", params={"tab": "appearance"})
    assert r.status_code == 200
    assert '<base href="./">' in r.text
