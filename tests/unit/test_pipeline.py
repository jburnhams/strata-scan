"""The stages on a 4-scan book made in the test, with the real Tesseract standing in for strata-models (the `runner` fixture): what a
person gets (pages, text, pictures, kinds, labels, files) and that their hand work survives a second run."""

import os

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from stratascan import files, pipeline, store
from stratascan.db.models import Book, Figure, Page, Scan


def pages_of(book_id):
    with store.session() as s:
        return list(s.scalars(select(Page).where(Page.book_id == book_id).order_by(Page.position)))


def book(book_id):
    with store.session() as s:
        return s.get(Book, book_id)


def test_a_whole_book(runner, make_book):
    b = make_book()
    runner.run(pipeline.Task(b, pipeline.STAGES))
    assert book(b).stage == "idle"
    assert book(b).error is None
    assert book(b).done == book(b).total
    ps = pages_of(b)
    assert [p.position for p in ps] == [1, 2, 3, 4]
    assert [p.kind for p in ps] == ["cover", "text", "text", "text"]
    tilted = ps[1]
    assert tilted.angle == pytest.approx(-1.5, abs=0.4)
    assert tilted.confidence > 0.9
    assert "puppets" in (tilted.text or "")
    assert tilted.label == "27"
    assert tilted.ocr_conf
    assert tilted.ocr_conf > 60
    with store.session() as s:
        figs = list(s.scalars(select(Figure).where(Figure.page_id == ps[2].id)))
    assert len(figs) == 1
    assert os.path.isfile(files.figure_png(b, figs[0].id))
    for p in ps:
        assert os.path.isfile(files.page_png(b, p.id))
        assert os.path.isfile(files.preview(b, "thumb", p.id))
    out = os.path.join(files.book_dir(b), "export")
    assert sorted(os.listdir(out)) == ["book.md", "book.pdf", "book.txt", "book.zip", "figures"]
    with open(os.path.join(out, "book.md"), encoding="utf8") as f:
        md = f.read()
    assert md.startswith("# Punch and Judy")
    assert "figures/p003-1.png" in md
    assert "PUPPET-PLAYS" not in md


def test_hand_work_survives_detect_and_read(runner, make_book):
    b = make_book()
    runner.run(pipeline.Task(b, ("import", "detect", "read")))
    p = pages_of(b)[1]
    with store.session() as s:
        row = s.get(Page, p.id)
        row.hand, row.crop_w, row.text, row.text_edited, row.kind = True, 900, "My text", True, "skip"
        s.add(Figure(page_id=p.id, x=1, y=2, w=30, h=40, hand=True))
    runner.run(pipeline.Task(b, ("detect", "read"), (p.id,)))
    after = next(x for x in pages_of(b) if x.id == p.id)
    assert (after.crop_w, after.text, after.kind) == (900, "My text", "skip")
    with store.session() as s:
        assert [(f.x, f.hand) for f in s.scalars(select(Figure).where(Figure.page_id == p.id))] == [(1, True)]


def test_failures_are_said_in_words(make_book, tmp_path):
    def down(path, pdf, lang, dpi):
        raise pipeline.StageError("strata-models is not running")

    r = pipeline.Runner(ocr=down)
    b = make_book()
    r.run(pipeline.Task(b, ("read",)))
    assert book(b).error == "the book has no pages: find them first"
    assert book(b).stage == "idle"
    r.run(pipeline.Task(b, ("detect",)))
    assert book(b).error == "the book has no scans: import it first"
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    assert book(b).error
    assert "4 of 4 pages could not be read: strata-models is not running" in book(b).error
    assert all(p.error == "strata-models is not running" for p in pages_of(b))
    with store.session() as s:
        s.get(Book, b).source = str(tmp_path / "gone.pdf")
    r.run(pipeline.Task(b, ("import",)))
    assert "there is nothing at" in (book(b).error or "")


def test_the_runner_thread_queues_resumes_and_refuses_unknown_stages(runner, make_book):
    b = make_book()
    with pytest.raises(ValueError, match="no stage 'bake'"):
        runner.submit(b, ["bake"])
    runner.start()
    runner.start()  # a second start is a no-op
    try:
        runner.submit(b, ["import", "detect"])
        assert runner.wait_idle(120)
        assert runner.idle()
        assert len(pages_of(b)) == 4
        with store.session() as s:
            s.get(Book, b).stage = "read"  # as if the server stopped mid-read
        runner.resume()
        assert runner.wait_idle(120)
        assert all(p.ocr is not None for p in pages_of(b))
        assert book(b).stage == "idle"
    finally:
        runner.stop()


def test_clean_text_and_keep_line():
    good = {"text": "the puppets were", "conf": 90, "words": [{"conf": 90}, {"conf": 92}, {"conf": 88}]}
    smudged = {
        "text": "the puppets wcre",
        "conf": 60,
        "words": [{"conf": 90}, {"conf": 70}, {"conf": 20}],
    }  # passes the text bar (55), not the cover bar (75)
    noise = {"text": ", iy VevrytnNiy Wu", "conf": 20, "words": [{"conf": 20}, {"conf": 25}, {"conf": 15}]}
    lone = {"text": "q", "conf": 96, "words": [{"conf": 96}]}
    ocr = {"lines": [good, smudged, noise, lone]}
    assert pipeline.clean_text(ocr, 5) == "the puppets were\nthe puppets wcre"
    assert pipeline.clean_text(ocr, 2) == ""
    assert pipeline.clean_text(ocr, 5, "cover") == "the puppets were"


def test_a_page_whose_scan_is_gone_cannot_be_drawn(make_book, runner):
    b = make_book()
    runner.run(pipeline.Task(b, ("import", "detect")))
    p = pages_of(b)[0]
    with store.session() as s:
        s.delete(s.get(Scan, p.scan_id))
    with pytest.raises(pipeline.StageError, match="has no scan"):
        pipeline.render(p)
    with pytest.raises(pipeline.StageError, match="cannot read the picture"):
        pipeline.read_image(os.path.join(files.book_dir(b), "nothing.png"))


def test_a_book_exported_before_it_is_read_is_its_pictures_at_their_paper_size(make_book, runner):
    b = make_book()
    runner.run(pipeline.Task(b, ("import", "detect", "export")))
    pdf = PdfReader(os.path.join(files.book_dir(b), "export", "book.pdf"))
    assert len(pdf.pages) == len(pages_of(b))
    box = pdf.pages[1].mediabox  # a text page: 1240 x 1754 pixels at 150 dpi is 595 x 842 points (A5-ish)
    assert abs(float(box.width) - 1240 / 150 * 72) < 6
    assert abs(float(box.height) - 1754 / 150 * 72) < 6
    assert pdf.metadata is not None
    assert pdf.metadata.title == book(b).title
