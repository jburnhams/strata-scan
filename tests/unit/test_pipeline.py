"""The stages on a 4-scan book made in the test, with the real Tesseract standing in for strata-models (the `runner` fixture): what a
person gets (pages, text, pictures, kinds, labels, files) and that their hand work survives a second run."""

import os
import shutil
import zipfile

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from stratascan import export, files, layout, pipeline, store
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


def test_typed_text_or_a_drawn_picture_alone_keeps_a_page_through_detect(runner, make_book):
    b = make_book()
    runner.run(pipeline.Task(b, ("import", "detect", "read")))
    typed, drawn = pages_of(b)[1:3]
    with store.session() as s:
        row = s.get(Page, typed.id)
        row.text, row.text_edited = "My text", True
        s.add(Figure(page_id=drawn.id, x=1, y=2, w=30, h=40, caption="Punch", hand=True))
    runner.run(pipeline.Task(b, ("detect", "read")))
    after = {p.id: p for p in pages_of(b)}
    assert after[typed.id].text == "My text"
    with store.session() as s:
        assert [f.caption for f in s.scalars(select(Figure).where(Figure.page_id == drawn.id, Figure.hand))] == [
            "Punch"
        ]


def test_a_task_for_one_page_follows_its_scan_through_detect(runner, make_book):
    b = make_book()
    runner.run(pipeline.Task(b, ("import", "detect")))
    p = min(pages_of(b), key=lambda x: x.id)  # not the newest row, so SQLite gives its replacement a new id
    runner.run(pipeline.Task(b, ("detect", "read"), (p.id,)))
    assert book(b).error is None
    again = [x for x in pages_of(b) if x.scan_id == p.scan_id]
    assert [x.id for x in again] != [p.id]  # detect made new pages for the scan
    assert all(x.ocr is not None for x in again)
    assert all(x.ocr is None for x in pages_of(b) if x.scan_id != p.scan_id)


def test_failures_are_said_in_words(make_book, tmp_path):
    def down(path, pdf, lang, dpi):
        raise pipeline.StageError("strata-models is not running")

    r = pipeline.Runner(ocr=down, correct=None, run_model=None)
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
    r.run(pipeline.Task(b, ("read", "export")))  # the export succeeds, and the failed read is still said
    assert "could not be read" in (book(b).error or "")
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


# ---- the correction pass -----------------------------------------------------------------------------------------------------------------
def test_text_pages_are_corrected_and_both_texts_kept(make_book, monkeypatch):
    """A text page's text is the correction (here: Tesseract's words in capitals), and the result keeps both; pictures, covers and blanks
    are not sent; a page a person typed is never replaced."""
    from books import tesseract_ocr

    sent = []

    def upper(path, text, model):
        sent.append((path, text, model))
        return text.upper()

    r = pipeline.Runner(ocr=tesseract_ocr, correct=upper, reread=None, run_model=None)
    b = make_book()
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    texts = [p for p in pages_of(b) if p.kind == "text" and p.ocr and p.ocr["corrected"]]
    assert texts
    assert sent
    assert all(m == "claude-haiku-5-5-api" for _, _, m in sent)
    assert len(sent) == len(texts)  # no cover, picture or blank page was sent
    for p in texts:
        assert p.text == p.ocr["corrected"]["text"]
        assert p.text == p.text.upper()
        assert p.ocr["corrected"]["model"] == "claude-haiku-5-5-api"
    r.run(
        pipeline.Task(b, ("export",))
    )  # the corrected lines are what the Markdown says, not dropped for not matching the OCR's
    with open(os.path.join(files.book_dir(b), "export", "book.md"), encoding="utf8") as f:
        md = f.read()
    assert "PUPPETS" in md
    assert "puppets" not in md
    with store.session() as s:
        s.get(Page, texts[0].id).text, s.get(Page, texts[0].id).text_edited = "typed by hand", True
    sent.clear()
    r.run(pipeline.Task(b, ("read",)))
    assert len(sent) == len(texts) - 1
    assert next(p for p in pages_of(b) if p.id == texts[0].id).text == "typed by hand"


def test_a_failed_or_implausible_correction_keeps_the_ocr_text(make_book, monkeypatch):
    from books import tesseract_ocr

    def down(path, text, model):
        raise pipeline.StageError("strata-models could not correct the page: out of memory")

    b = make_book()
    pipeline.Runner(ocr=tesseract_ocr, correct=down, reread=None, run_model=None).run(
        pipeline.Task(b, ("import", "detect", "read"))
    )
    texts = [p for p in pages_of(b) if p.kind == "text" and p.ocr and p.ocr.get("corrected")]
    assert texts
    assert all("out of memory" in p.ocr["corrected"]["error"] for p in texts)
    assert all(p.text and p.error is None for p in texts)  # Tesseract's text, and no page error
    pipeline.Runner(
        ocr=tesseract_ocr, correct=lambda path, text, model: "A page of a book.", reread=None, run_model=None
    ).run(pipeline.Task(b, ("read",)))
    after = [p for p in pages_of(b) if p.id in {t.id for t in texts}]
    assert all("kept the OCR text" in p.ocr["corrected"]["error"] and p.text != "A page of a book." for p in after)
    monkeypatch.setenv("STRATASCAN_CORRECT", "off")
    called = []
    pipeline.Runner(ocr=tesseract_ocr, correct=lambda *a: called.append(a) or "", reread=None, run_model=None).run(
        pipeline.Task(b, ("read",))
    )
    assert called == []
    assert all(p.ocr["corrected"] is None for p in pages_of(b) if p.ocr)


def test_plausible_corrections_stay_near_the_texts_length():
    text = "Punch and Judy, with instructions how to manage the little wooden actors"
    assert pipeline.plausible(text, text.replace("Judy", "JUDY"))
    assert not pipeline.plausible(text, "")
    assert not pipeline.plausible(text, "Punch")
    assert not pipeline.plausible(text, text + " This page shows the title of a book about puppets and their history.")


# ---- the second reading, the layout and the rebuilt pages ----------------------------------------------------------------------------------


def test_the_correction_is_of_the_cleaned_pages_text_unless_cleaning_lost_the_page(make_book):
    from books import tesseract_ocr

    sent = []

    def keep(path, text, model):
        sent.append(text)
        return text

    clean = lambda path, lang, dpi: {  # noqa: E731
        "lines": [{"text": "The cleaned page read again", "conf": 95, "words": [{"conf": 95}] * 5}] * 12
    }
    b = make_book()
    pipeline.Runner(ocr=tesseract_ocr, correct=keep, reread=clean, run_model=None).run(
        pipeline.Task(b, ("import", "detect", "read"))
    )
    assert sent
    assert all(t.startswith("The cleaned page read again") for t in sent)
    sent.clear()
    lost = lambda path, lang, dpi: {"lines": [{"text": "few words", "conf": 95, "words": [{"conf": 95}] * 2}]}  # noqa: E731
    pipeline.Runner(ocr=tesseract_ocr, correct=keep, reread=lost, run_model=None).run(pipeline.Task(b, ("read",)))
    assert sent
    assert not any(t.startswith("few words") for t in sent)  # Tesseract's first reading instead

    def down(path, lang, dpi):
        raise pipeline.StageError("strata-models could not read the cleaned page: gone")

    pipeline.Runner(ocr=tesseract_ocr, correct=keep, reread=down, run_model=None).run(pipeline.Task(b, ("read",)))
    assert any("gone" in p.ocr["corrected"]["error"] for p in pages_of(b) if p.ocr and p.ocr.get("corrected"))


def test_a_text_page_is_laid_out_and_set_again(make_book, fake_models, monkeypatch):
    """layout -> groups -> rebuild, through the real client: the roles, models and presets the evals measured, in order; the export has both
    PDFs, and re-reading a page removes what was set from the old reading."""
    from books import tesseract_ocr

    fake_models.results = models_answers(fake_models)
    r = pipeline.Runner(ocr=tesseract_ocr, correct=None, reread=None, run_model=layout.models_run)
    b = make_book()
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    texts = [p for p in pages_of(b) if p.kind == "text" and p.ocr and p.ocr["layout"]]
    assert texts
    assert all(p.ocr["layout"]["model"] == "claude-opus-5-5-api" and p.ocr["layout"]["blocks"] for p in texts)
    asked = [j for j in fake_models.jobs if j["role"] == "vision-language"]
    assert {(j["model"], j["params"]["preset"]) for j in asked} == {("claude-opus-5-5-api", "page-layout-fix-v2")}
    assert len(asked) == len(
        texts
    )  # each page's layout asked once, all of them in one bulk call before any page was finished
    first = min(j["id"] for j in asked)
    assert [j["id"] for j in asked] == list(range(first, first + len(asked)))
    fake_models.jobs.clear()
    r.run(pipeline.Task(b, ("rebuild", "export")))
    draws = [j for j in fake_models.jobs if j["role"] == "page-build" and j["params"].get("texts") is not None]
    assert len(draws) == len(texts)
    assert all(j["model"] == "pagebuild" and j["params"]["font_fit"] and j["params"]["snap"] == 0.1 for j in draws)
    assert all(
        j["params"]["styles"] == ["roman", "italic"] and j["params"]["crop"] and j["params"]["rules"] for j in draws
    )
    asked = [j for j in fake_models.jobs if j["role"] == "vision-language"]
    assert {j["params"].get("preset") or j["params"].get("system_preset") for j in asked} == {
        "page-text-fix-v1",
        "ocr-read-v2",
    }
    assert len(asked) == 2 * len(texts)  # queued ahead: none asked again when its page was set
    assert max(j["id"] for j in asked) < min(j["id"] for j in draws)  # all before the first page was drawn
    assert all(os.path.isfile(files.rebuilt_pdf(b, p.id)) for p in texts)
    assert os.path.isfile(files.export(b, "book-rebuilt.pdf"))
    with zipfile.ZipFile(files.export(b, "book.zip")) as z:
        assert "book-rebuilt.pdf" in z.namelist()
    r.run(pipeline.Task(b, ("read", "export")))
    assert not any(os.path.isfile(files.rebuilt_pdf(b, p.id)) for p in texts)
    assert not os.path.isfile(files.export(b, "book-rebuilt.pdf"))


def test_the_finished_pdf_has_the_pages_that_pass_and_the_scans_of_those_that_do_not(make_book, fake_models):
    """Every rebuilt page goes through the real gate, worst read first: one that says and shows what its scan does stands in the finished PDF (the
    stand-in "sets" a page as Tesseract's own PDF of it, its picture over its words), and a page whose words were not drawn keeps its scan."""
    from books import tesseract_ocr

    answers = models_answers(fake_models)
    r = pipeline.Runner(ocr=tesseract_ocr, correct=None, reread=None, run_model=layout.models_run)
    b = make_book()
    fake_models.results = answers
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    texts = [p for p in pages_of(b) if p.kind == "text" and p.ocr and p.ocr["layout"]]
    assert len(texts) > 1
    worst = min(texts, key=lambda p: p.ocr_conf)
    draw, order = answers["page-build"], []

    def page_build(params):
        got = draw(params)
        pid = int(os.path.basename(params.get("out", "0")).split(".")[0]) if params.get("font_fit") else 0
        if pid:
            order.append(pid)
            if pid != worst.id:
                shutil.copyfile(files.ocr_pdf(b, pid), params["out"])
        return got

    fake_models.results = {**answers, "page-build": page_build}
    r.run(pipeline.Task(b, ("rebuild", "export")))
    assert order[0] == worst.id
    by_id = {p.id: p for p in pages_of(b)}
    assert by_id[worst.id].ocr["gate"]["passed"] is False
    assert by_id[worst.id].ocr["gate"]["reasons"][0].startswith("100.0% of the words are missing")
    assert export.stands(b, by_id[worst.id]) is False
    good = [by_id[p.id] for p in texts if p.id != worst.id]
    assert [(p.ocr["gate"]["reasons"], export.stands(b, p)) for p in good] == [([], True)] * len(good)
    finished = PdfReader(files.export(b, "book-rebuilt.pdf")).pages
    assert len(finished) == len([p for p in by_id.values() if p.kind != "skip"])
    assert all(p.mediabox.width != 100 for p in finished)  # the stand-in's blank 100-point page is not among them


def test_a_page_that_fails_is_set_again_from_its_rows_and_kept_only_when_it_passes(make_book, fake_models):
    """The reader misses a line of every page that the corrected text has. The first setting of every page lacks its words; the second, of the
    lines put on their rows, is the page as Tesseract's own PDF of it, but for one page whose second setting lacks them too."""
    from books import tesseract_ocr

    missed: dict[str, str] = {}

    def misses_a_line(path, pdf, lang, dpi):
        got = tesseract_ocr(path, pdf, lang, dpi)
        if len(got["lines"]) > 5:
            missed[path] = "\n".join(ln["text"] for ln in got["lines"])
            got["lines"] = got["lines"][:3] + got["lines"][4:]
        return got

    def correct(path, text, model):
        return missed.get(path, text)

    answers = models_answers(fake_models)
    fake_models.results = answers
    r = pipeline.Runner(ocr=misses_a_line, correct=correct, reread=None, run_model=layout.models_run)
    b = make_book()
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    texts = [p for p in pages_of(b) if p.kind == "text" and p.ocr and p.ocr["layout"] and len(p.text.splitlines()) > 5]
    assert len(texts) > 1
    bad = texts[0].id
    draw = answers["page-build"]

    def page_build(params):
        got = draw(params)
        out = os.path.basename(params.get("out", ""))
        pid = int(out.split(".")[0]) if params.get("font_fit") else 0
        if pid and (out.endswith(".rows.pdf") and pid != bad):
            shutil.copyfile(files.ocr_pdf(b, pid), params["out"])
        return got

    fake_models.results = {**answers, "page-build": page_build}
    r.run(pipeline.Task(b, ("rebuild",)))
    by_id = {p.id: p for p in pages_of(b)}
    for p in texts:
        g = by_id[p.id].ocr["gate"]
        assert g["passed"] is (p.id != bad)
        assert g["lines_put_right"] == (0 if p.id == bad else 1)
        assert bool(g["from_rows"]) is (p.id == bad)
        assert not os.path.exists(files.rebuilt_pdf(b, p.id) + ".rows.pdf")


def test_a_layout_that_fails_leaves_the_page_read_and_says_why(make_book, fake_models):
    from books import tesseract_ocr

    fake_models.results = models_answers(fake_models)
    fake_models.results["vision-language"] = {"text": "no", "model": "m"}
    r = pipeline.Runner(ocr=tesseract_ocr, correct=None, reread=None, run_model=layout.models_run)
    b = make_book()
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    texts = [p for p in pages_of(b) if p.kind == "text" and p.ocr and p.ocr["layout"]]
    assert texts
    assert all("not JSON" in p.ocr["layout"]["error"] and p.text for p in texts)
    r.run(pipeline.Task(b, ("rebuild",)))
    with store.session() as s:
        assert "could not be set again: the model's answer was not JSON" in s.get(Book, b).error
    pipeline.Runner(ocr=tesseract_ocr, correct=None, run_model=None).run(pipeline.Task(b, ("rebuild",)))
    with store.session() as s:
        assert "strata-models is not set up" in s.get(Book, b).error


def test_a_rebuild_needs_read_pages_and_a_stop_in_it_is_finished_not_restarted(make_book, runner):
    b = make_book()
    runner.run(pipeline.Task(b, ("import", "detect")))
    with pytest.raises(pipeline.StageError, match="read the book first"):
        runner.stage_rebuild(b)
    assert pipeline.resume_from("rebuild") == ("rebuild", "export")
    assert pipeline.resume_from("read") == ("read", "export")
    assert pipeline.resume_from("???") == ("detect", "read")


def models_answers(service):
    """strata-models' answers for the layout roles, from what each job is sent (the real page-build draws; this writes a small PDF)."""

    def page_build(params):
        ocr = params["ocr"]
        if params.get("list_lines"):
            rows = [f"{n} b1 [0,0,9,9] {ln['text']}" for n, ln in enumerate(ocr["lines"], 1)]
            return {"text": "\n".join(rows)}
        out = params["out"]
        with open(out, "wb") as f:
            from pypdf import PdfWriter

            w = PdfWriter()
            w.add_blank_page(100, 100)
            w.write(f)
        blocks = [{"role": "body", "lines": [{"box": ln["box"]} for ln in ocr["lines"]]}]
        return {"pdf": out, "page": {"width": 10, "height": 10, "blocks": blocks}}

    def ask(params):
        if params.get("system_preset") == "ocr-read-v2":
            return {"text": ""}  # no reading: the gate goes by the page's text
        if params["preset"] == "page-text-fix-v1":
            return {"json": {"lines": []}, "text": "{}"}
        return {"json": {"blocks": [{"lines": [1], "role": "body"}], "figures": []}, "text": "{}"}

    return {
        "page-build": page_build,
        "vision-language": ask,
        "font-match": {"face": "tinos", "blocks": [], "fonts": {}},
    }
