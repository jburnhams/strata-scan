"""The HTTP API as the web app uses it, on the real server (`base_url`: uvicorn on a loopback port, the pipeline thread running, pages
read through the strata-models stand-in): upload a PDF, wait for the book, fix a page by hand, export, download."""

import io
import time
import zipfile

import httpx
from books import book_pdf


def wait_idle(c: httpx.Client, book_id: int, timeout: float = 240) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        b = c.get(f"/api/books/{book_id}").json()
        if b["stage"] == "idle":
            return b
        time.sleep(0.3)
    raise AssertionError(f"book {book_id} still busy: {b}")


def test_a_book_through_the_api(base_url, tmp_path):
    src = book_pdf(str(tmp_path / "punch.pdf"))
    with httpx.Client(base_url=base_url, timeout=60) as c:
        with open(src, "rb") as f:
            r = c.post(
                "/api/books/upload", files={"file": ("punch.pdf", f, "application/pdf")}, data={"title": "Punch"}
            )
        assert r.status_code == 201
        book = r.json()
        assert c.delete(f"/api/books/{book['id']}").status_code == 409  # busy: the stages are running
        done = wait_idle(c, book["id"])
        assert done["error"] is None
        assert (done["pages"], done["read"]) == (4, 4)
        assert set(done["files"]) == {"book.md", "book.txt", "book.pdf", "book.zip"}

        pages = c.get(f"/api/books/{book['id']}/pages").json()
        text = next(p for p in pages if p["kind"] == "text")
        page = c.get(f"/api/pages/{text['id']}").json()
        assert "puppets" in page["text"]
        assert c.get(f"/api/pages/{text['id']}/image", params={"size": "thumb"}).headers["content-type"] == "image/jpeg"

        # a person's crop is kept and the page is read again with it
        crop = page["crop"]
        smaller = {"x": crop["x"] + 10, "y": crop["y"] + 10, "w": crop["w"] - 20, "h": crop["h"] - 20}
        assert c.patch(f"/api/pages/{text['id']}", json={"crop": smaller}).json()["hand"] is True
        wait_idle(c, book["id"])
        again = c.get(f"/api/pages/{text['id']}").json()
        assert again["crop"] == smaller
        assert "puppets" in again["text"]

        # a typed correction survives a re-read, and pictures drawn by hand are kept
        c.patch(f"/api/pages/{text['id']}", json={"text": "The puppets, corrected."})
        figs = c.put(
            f"/api/pages/{text['id']}/figures", json={"figures": [{"x": 20, "y": 20, "w": 200, "h": 150}]}
        ).json()
        assert len(figs) == 1
        assert c.post(f"/api/books/{book['id']}/run", json={"stages": ["read", "export"]}).status_code == 202
        wait_idle(c, book["id"])
        assert c.get(f"/api/pages/{text['id']}").json()["text"] == "The puppets, corrected."
        assert c.get(f"/api/figures/{figs[0]['id']}/image").status_code == 200

        z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/books/{book['id']}/files/book.zip").content))
        assert {"book.md", "book.txt", "book.pdf"} <= set(z.namelist())
        assert "The puppets, corrected." in z.read("book.md").decode()
        assert c.post(f"/api/books/{book['id']}/run", json={"stages": ["polish"]}).status_code == 400
        assert c.delete(f"/api/books/{book['id']}").json() == {"removed": book["id"]}
        assert c.get("/api/books").json() == []


def test_system_and_settings(client, monkeypatch):
    monkeypatch.setenv("STRATA_MODELS_URL", "http://127.0.0.1:9")
    s = client.get("/api/system").json()
    assert s["models"]["available"] is False  # nothing listens on port 9
    assert (
        client.put("/api/settings", json={"workers": "2"}).json()["workers"] == "2"
    )  # settings are stored as text (strata_python.settings)
    assert client.put("/api/settings", json={"data_dir": "relative"}).status_code == 400


def test_a_reload_on_any_screen_gets_the_app(client):
    r = client.get("/books/3/pages/7", params={"tab": "text"})
    assert r.status_code == 200
    assert '<base href="../../../">' in r.text
