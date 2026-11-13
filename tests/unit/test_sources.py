"""sources.py: what can be imported, at what resolution, in what order; PDFs made in the test, pictures in tmp_path."""

import os

import pytest
from books import book_pdf, page

from stratascan import sources


def test_describe_says_what_cannot_be_imported(tmp_path):
    with pytest.raises(sources.SourceError, match="full path"):
        sources.describe("book.pdf")
    with pytest.raises(sources.SourceError, match="nothing at"):
        sources.describe(str(tmp_path / "none.pdf"))
    (tmp_path / "empty").mkdir()
    with pytest.raises(sources.SourceError, match="no pictures"):
        sources.describe(str(tmp_path / "empty"))
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(sources.SourceError, match="not a PDF or a picture"):
        sources.describe(str(tmp_path / "notes.txt"))
    (tmp_path / "bad.pdf").write_text("not a pdf")
    with pytest.raises(sources.SourceError, match=r"cannot be read|not a PDF"):
        sources.describe(str(tmp_path / "bad.pdf"))
    assert sources.pdf_title(str(tmp_path / "bad.pdf")) is None


def test_a_pdf_is_drawn_at_the_resolution_of_its_scans(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATASCAN_DATA", str(tmp_path / "data"))
    src = book_pdf(str(tmp_path / "b.pdf"), [page(), page()])
    assert sources.describe(src) == ("pdf", 2)
    seen = []
    scans = sources.import_scans(src, 7, 600, lambda d, t: seen.append((d, t)))
    assert seen == [(1, 2), (2, 2)]
    assert [(s.position, s.file, s.dpi) for s in scans] == [(1, "scans/0001.png", 150), (2, "scans/0002.png", 150)]
    assert abs(scans[0].width - page().width) <= 1
    assert abs(scans[0].height - page().height) <= 1
    capped = sources.import_scans(src, 8, 100)
    assert capped[0].dpi == 100
    assert capped[0].width < page().width


def test_a_folder_of_pictures_in_page_order(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATASCAN_DATA", str(tmp_path / "data"))
    folder = tmp_path / "pics"
    folder.mkdir()
    for name in ("p10.jpg", "p2.png", "p1.tif", ".hidden.png"):
        page().resize((200, 280)).save(folder / name, dpi=(300, 300))
    assert sources.describe(str(folder)) == ("pictures", 3)
    scans = sources.import_scans(str(folder), 3, 600)
    assert [s.file for s in scans] == ["scans/0001.png", "scans/0002.png", "scans/0003.jpg"]  # p1 (tif -> png), p2, p10
    assert scans[0].dpi == 300
    assert os.path.isfile(tmp_path / "data" / "books" / "3" / "scans" / "0003.jpg")
    one = sources.import_scans(str(folder / "p2.png"), 4, 600)
    assert len(one) == 1
    assert sources.describe(str(folder / "p2.png")) == ("pictures", 1)
    (folder / "broken.png").write_text("no")
    with pytest.raises(sources.SourceError, match=r"broken\.png"):
        sources.import_scans(str(folder), 5, 600)


def test_pdf_title(tmp_path):
    im = page()
    p = str(tmp_path / "t.pdf")
    im.save(p, "PDF", title="Punch and Judy")
    assert sources.pdf_title(p) == "Punch and Judy"
