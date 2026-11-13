"""The HTTP API over a real database and data folder, with the runner's OCR done by the real Tesseract (the `runner` fixture)."""

import io

import pytest
import uvicorn
from books import book_pdf, on_bed, page
from fastapi.testclient import TestClient
from PIL import Image

from stratascan.server import app as server_app
from stratascan.server.app import create_app


@pytest.fixture
def api(runner):
    with TestClient(create_app(runner)) as c:
        c.runner = runner
        yield c


def done(api, book_id):
    assert api.runner.wait_idle(180)
    return api.get(f"/api/books/{book_id}").json()


def test_landing_page_and_built_static_index(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, "STATIC", str(tmp_path / "no_static"))
    c = TestClient(create_app(migrate=False))
    assert "strata-scan" in c.get("/").text
    assert c.get("/api/health").json()["ok"] is True
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<h1>built react app</h1>", encoding="utf8")
    (static / "assets" / "main.js").write_text("console.log(1)", encoding="utf8")
    monkeypatch.setattr(server_app, "STATIC", str(static))
    c2 = TestClient(create_app(migrate=False))
    assert c2.get("/books/1").text == '<base href="../"><h1>built react app</h1>'
    assert "console.log(1)" in c2.get("/assets/main.js").text
    assert c2.get("/api/nope").status_code == 404


def test_a_book_from_a_path_through_to_its_files(api, tmp_path):
    src = book_pdf(str(tmp_path / "b.pdf"))
    assert api.post("/api/books", json={"source": "b.pdf"}).status_code == 400
    b = api.post("/api/books", json={"source": src, "title": " ", "author": "J. P. Collier"}).json()
    assert b["title"] == "b"
    assert b["author"] == "J. P. Collier"
    assert b["stage"] in ("import", "detect", "read", "export", "idle")
    b = done(api, b["id"])
    assert (b["stage"], b["error"], b["scans"], b["pages"], b["read"], b["figures"]) == ("idle", None, 4, 4, 4, 1)
    assert set(b["files"]) == {"book.md", "book.txt", "book.pdf", "book.zip"}
    assert [x["id"] for x in api.get("/api/books").json()] == [b["id"]]
    pages = api.get(f"/api/books/{b['id']}/pages").json()
    assert [p["kind"] for p in pages] == ["cover", "text", "text", "text"]
    assert pages[2]["figures"] == 1
    full = api.get(f"/api/pages/{pages[1]['id']}").json()
    assert "puppets" in full["text"]
    assert full["lines"]
    assert full["prev_id"] == pages[0]["id"]
    assert full["next_id"] == pages[2]["id"]
    assert full["scan"]["dpi"] == 150
    assert len(full["siblings"]) == 1
    figs = api.get(f"/api/books/{b['id']}/figures").json()
    assert figs[0]["page_position"] == 3
    for url in (
        f"/api/figures/{figs[0]['id']}/image",
        f"/api/pages/{pages[1]['id']}/image?size=thumb",
        f"/api/pages/{pages[1]['id']}/image?size=full",
    ):
        r = api.get(url)
        assert r.status_code == 200
        assert Image.open(io.BytesIO(r.content)).width > 10
    r = api.get(f"/api/scans/{full['scan']['id']}/image?angle=2")
    assert r.headers["content-type"] == "image/jpeg"
    assert 0.5 < float(r.headers["x-scale"]) <= 1.0
    r = api.get(f"/api/books/{b['id']}/files/book.md")
    assert r.text.startswith("# b")
    assert 'filename="b.md"' in r.headers["content-disposition"]
    assert api.get(f"/api/books/{b['id']}/files/nope.exe").status_code == 404


def test_upload_edit_pages_and_remove(api, tmp_path):
    pdf = book_pdf(str(tmp_path / "u.pdf"), [on_bed(page()), on_bed(page())])
    assert api.post("/api/books/upload", files={"file": ("notes.txt", b"x")}).status_code == 400
    with open(pdf, "rb") as f:
        b = api.post(
            "/api/books/upload", files={"file": ("Punch.pdf", f, "application/pdf")}, data={"title": "Punch"}
        ).json()
    assert b["title"] == "Punch"
    done(api, b["id"])
    p1, p2 = api.get(f"/api/books/{b['id']}/pages").json()
    # metadata
    assert api.patch(f"/api/books/{b['id']}", json={"title": " "}).status_code == 422
    assert (
        api.patch(f"/api/books/{b['id']}", json={"title": "Punch and Judy", "author": "", "lang": "eng"}).json()[
            "author"
        ]
        is None
    )
    # kind, label and text, and a bad kind
    assert api.patch(f"/api/pages/{p1['id']}", json={"kind": "bake"}).status_code == 422
    r = api.patch(f"/api/pages/{p1['id']}", json={"kind": "skip", "label": "ii", "text": "Corrected."}).json()
    assert (r["kind"], r["label"], r["text"], r["text_edited"]) == ("skip", "ii", "Corrected.", True)
    # a new turn: hand work, drawn and read again
    r = api.patch(f"/api/pages/{p2['id']}", json={"angle": 1.0}).json()
    assert r["hand"]
    assert r["angle"] == 1.0
    assert api.post(f"/api/books/{b['id']}/run", json={"stages": ["read"]}).status_code in (202, 409)
    done(api, b["id"])
    assert api.get(f"/api/pages/{p2['id']}").json()["read"]
    # the first scan becomes a spread by hand; the corrected text stays with... nothing, it was a single page
    scan = api.get(f"/api/pages/{p1['id']}").json()["scan"]
    bad = {
        "pages": [
            {"side": "left", "crop": {"x": 0, "y": 0, "w": 10, "h": 10}},
            {"side": "left", "crop": {"x": 0, "y": 0, "w": 10, "h": 10}},
        ]
    }
    assert api.put(f"/api/scans/{scan['id']}/pages", json=bad).status_code == 422
    half = scan["width"] // 2
    made = api.put(
        f"/api/scans/{scan['id']}/pages",
        json={
            "pages": [
                {"side": "left", "crop": {"x": 0, "y": 0, "w": half, "h": scan["height"]}},
                {"side": "right", "crop": {"x": half, "y": 0, "w": half, "h": scan["height"] + 99}},
            ]
        },
    ).json()
    assert [m["side"] for m in made] == ["left", "right"]
    assert [m["position"] for m in made] == [1, 2]
    done(api, b["id"])
    assert [p["position"] for p in api.get(f"/api/books/{b['id']}/pages").json()] == [1, 2, 3]
    # pictures by hand
    figs = api.put(
        f"/api/pages/{made[0]['id']}/figures",
        json={"figures": [{"x": 10, "y": 20, "w": 100, "h": 9999, "caption": " Mr Punch "}]},
    ).json()
    assert figs[0]["caption"] == "Mr Punch"
    assert figs[0]["hand"]
    assert figs[0]["y"] + figs[0]["h"] <= api.get(f"/api/pages/{made[0]['id']}").json()["size"]["h"] + 1
    assert api.get(f"/api/figures/{figs[0]['id']}/image").status_code == 200
    # 404s, a busy book, removal
    assert api.get("/api/books/999").status_code == 404
    assert api.get("/api/pages/999").status_code == 404
    assert api.patch("/api/pages/999", json={}).status_code == 404
    assert api.patch("/api/books/999", json={}).status_code == 404
    assert api.get("/api/scans/999/image").status_code == 404
    assert api.get("/api/figures/999/image").status_code == 404
    assert api.post(f"/api/books/{b['id']}/run", json={"stages": ["bake"]}).status_code == 400
    assert api.delete(f"/api/books/{b['id']}").json() == {"removed": b["id"]}
    assert api.get("/api/books").json() == []


def test_a_busy_book_refuses_changes(api, tmp_path, make_book):
    from stratascan import store
    from stratascan.db.models import Book

    b = make_book()
    with store.session() as s:
        s.get(Book, b).stage = "read"
    r = api.delete(f"/api/books/{b}")
    assert r.status_code == 409
    assert "busy (read)" in r.json()["detail"]
    assert api.get(f"/api/books/{b}/files/book.md").status_code == 404  # not made yet
    assert api.get("/api/pages/1/image").status_code == 404


def test_main_serves_on_the_default_port(monkeypatch):
    runs = []
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port, log_level: runs.append((host, port, log_level)))
    server_app.main(["--host", "127.0.0.1", "--port", "8368"])
    assert runs == [("127.0.0.1", 8368, "warning")]
