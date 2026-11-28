"""compare.py: a page's scan against its finished page. The measures on drawn pictures, then the files and the HTTP API over a book imported
and read for real (the `runner` fixture's Tesseract), with finished pages written as PDFs in the test."""

import os

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from stratascan import compare, files
from stratascan.db.models import Page
from stratascan.server.app import create_app

W, H = 400, 600


def lines(shift=0, rows=12, width=W, height=H):
    """A grey page of paper with dark bars for lines of type, `shift` pixels lower."""
    img = np.full((height, width), 225, np.uint8)
    for r in range(rows):
        y = 60 + 40 * r + shift
        img[y : y + 10, 40 : width - 40] = 25
    return img


def test_a_page_against_itself_agrees_fully():
    m = compare.measure(lines(), lines(), 150)
    assert m.ink == pytest.approx(1.0, abs=0.02)
    assert m.shape == 0
    assert m.ink_scan == pytest.approx(m.ink_finished, rel=0.15)


def test_lines_set_a_pixel_off_still_agree_but_lines_set_elsewhere_do_not():
    assert compare.measure(lines(), lines(shift=1), 150).ink > 0.9
    assert compare.measure(lines(), lines(shift=20), 150).ink < 0.2


def test_a_finished_page_of_another_shape_says_how_much():
    m = compare.measure(lines(), lines(height=480), 150)
    assert m.shape == pytest.approx(0.25, abs=0.01)


def fake_page(**kw):
    p = Page(book_id=1, scan_id=1, position=3, **kw)
    p.id = 7
    return p


@pytest.mark.parametrize(
    ("kind", "m", "verdict", "why"),
    [
        ("text", None, None, ["not set yet"]),
        ("text", compare.Match(0.9, 0.05, 0.05, 0.0), {"passed": True, "reasons": []}, []),
        (
            "text",
            compare.Match(0.9, 0.05, 0.05, 0.0),
            {"passed": False, "reasons": ["5% of words lost"]},
            ["5% of words lost"],
        ),
        ("text", compare.Match(0.3, 0.05, 0.05, 0.0), None, ["the ink agrees only 30%"]),
        ("picture", compare.Match(0.0, 0.2, 0.001, 0.0), None, ["the finished page has almost none of the scan's ink"]),
        ("blank", compare.Match(1.0, 0.0, 0.0, 0.0), None, []),
        ("text", compare.Match(0.9, 0.05, 0.05, 0.1), None, ["the finished page is 10% a different shape"]),
        (
            "cover",
            compare.Match(0.2, 0.3, 0.3, 0.2),
            None,
            [],
        ),  # trimmed to the book, a photograph: neither measure says anything
    ],
)
def test_faults_in_words(kind, m, verdict, why):
    assert compare.faults(fake_page(kind=kind), m, verdict) == why


def test_two_pages_side_by_side_at_the_taller_ones_height(tmp_path):
    a, b = str(tmp_path / "a.png"), str(tmp_path / "b.png")
    cv2.imwrite(a, np.zeros((100, 60, 3), np.uint8))
    cv2.imwrite(b, np.full((50, 40, 3), 255, np.uint8))
    s = compare.spread(a, b)
    assert s.shape == (100, 140, 3)
    assert s[0, 59].tolist() == [0, 0, 0]
    assert s[0, 60].tolist() == [255, 255, 255]
    assert compare.spread(a, None).shape == (100, 60, 3)
    with pytest.raises(FileNotFoundError):
        compare.spread(str(tmp_path / "none.png"), None)


def write_pdf(img: Image.Image, path: str) -> None:
    img.convert("RGB").save(path, "PDF", resolution=150)


def test_the_api_compares_each_page_and_keeps_what_it_worked_out(runner, make_book):
    book = make_book()
    with TestClient(create_app(runner)) as api:
        runner.submit(book, ("import", "detect", "read"))
        assert runner.wait_idle(180)
        pages = api.get(f"/api/books/{book}/pages").json()
        assert [p["kind"] for p in pages] == ["cover", "text", "text", "text"]
        good, lost = pages[1]["id"], pages[2]["id"]
        # page 2 finished as itself (a PDF of its own picture), page 3 as a blank sheet: its text gone
        write_pdf(Image.open(files.page_png(book, good)), files.rebuilt_pdf(book, good))
        write_pdf(Image.new("RGB", (W, int(W * 1.414)), "white"), files.rebuilt_pdf(book, lost))

        rows = {r["page_id"]: r for r in api.get(f"/api/books/{book}/compare").json()}
        assert len(rows) == 4
        assert rows[pages[0]["id"]]["why"] == ["not set yet"]
        assert rows[good]["finished"] is True
        assert rows[good]["match"]["ink"] > 0.8
        assert rows[good]["look"] is False
        assert rows[lost]["look"] is True
        assert "the finished page has almost none of the scan's ink" in rows[lost]["why"]

        kept = files.preview(book, "finished", good)
        assert os.path.isfile(kept)
        assert os.path.isfile(os.path.splitext(kept)[0] + ".json")
        made = os.path.getmtime(kept)
        assert api.get(f"/api/books/{book}/compare").json() == list(rows.values())
        assert os.path.getmtime(kept) == made  # read back, not drawn again

        r = api.get(f"/api/pages/{good}/finished")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        drawn = cv2.imread(kept)
        prev = cv2.imread(files.preview(book, "page", good))
        assert drawn.shape[1] == prev.shape[1]  # as wide as the scan's preview, so an overlay lines up
        assert api.get(f"/api/pages/{pages[0]['id']}/finished").status_code == 404

        both = api.get(f"/api/books/{book}/spread", params={"pages": f"{good},{lost}", "side": "finished"})
        assert both.status_code == 200
        assert both.headers["content-type"] == "image/jpeg"
        assert api.get(f"/api/books/{book}/spread", params={"pages": f"{good},{lost}"}).status_code == 200
        assert (
            api.get(f"/api/books/{book}/spread", params={"pages": f"{pages[0]['id']}", "side": "finished"}).status_code
            == 404
        )
        assert api.get(f"/api/books/{book}/spread", params={"pages": "99999"}).status_code == 404
        assert api.get(f"/api/books/{book}/spread", params={"pages": "x"}).status_code == 422
        assert api.get("/api/books/9999/compare").status_code == 404


def test_a_kept_result_is_worked_out_again_when_the_finished_page_changes(runner, make_book):
    book = make_book()
    with TestClient(create_app(runner)) as api:
        runner.submit(book, ("import", "detect", "read"))
        assert runner.wait_idle(180)
        p = api.get(f"/api/books/{book}/pages").json()[1]["id"]
        write_pdf(Image.new("RGB", (W, int(W * 1.414)), "white"), files.rebuilt_pdf(book, p))
        first = {r["page_id"]: r for r in api.get(f"/api/books/{book}/compare").json()}[p]
        assert first["look"] is True
        write_pdf(Image.open(files.page_png(book, p)), files.rebuilt_pdf(book, p))
        future = os.path.getmtime(files.preview(book, "finished", p)) + 5
        os.utime(files.rebuilt_pdf(book, p), (future, future))
        again = {r["page_id"]: r for r in api.get(f"/api/books/{book}/compare").json()}[p]
        assert again["look"] is False


def test_the_compare_command_lists_the_pages_to_look_at(runner, make_book, capsys):
    from stratascan import cli

    book = make_book()
    with TestClient(create_app(runner)):
        runner.submit(book, ("import", "detect", "read"))
        assert runner.wait_idle(180)
    assert cli.main(["compare", str(book)]) == 0
    out = capsys.readouterr().out
    assert out.count("not set yet") == 4
    assert out.strip().endswith("4 of 4 pages to look at")
    assert cli.main(["compare", str(book), "--json"]) == 0
    assert '"why"' in capsys.readouterr().out
    with pytest.raises(SystemExit, match="there is no book 999"):
        cli.main(["compare", "999"])
