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


def test_the_finished_pdf_sets_every_page_and_one_that_fails_is_flagged(make_book, fake_models):
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
    assert export.stands(b, by_id[worst.id]) is True  # set all the same, its best try: only blanks and covers are scans
    good = [by_id[p.id] for p in texts if p.id != worst.id]
    assert [(p.ocr["gate"]["reasons"], export.stands(b, p)) for p in good] == [([], True)] * len(good)
    finished = PdfReader(files.export(b, "book-rebuilt.pdf")).pages
    assert len(finished) == len([p for p in by_id.values() if p.kind != "skip"])
    assert all(
        os.path.isfile(files.rebuilt_pdf(b, p.id)) for p in by_id.values()
    )  # every page set again: none left a scan
    order.clear()
    fake_models.jobs.clear()
    r.run(
        pipeline.Task(b, ("rebuild",))
    )  # again: only the page that failed is set again, none made as it would be made now
    assert order == [worst.id]
    drawn = [j["params"]["out"] for j in fake_models.jobs if j["role"] == "page-build" and "out" in j["params"]]
    assert {int(os.path.basename(o).split(".")[0]) for o in drawn} == {
        worst.id
    }  # no picture, cover or blank page made again


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
    r.run(pipeline.Task(b, ("rebuild",)))  # laid out from their own lines instead, and set in type all the same
    with store.session() as s:
        assert s.get(Book, b).error is None
    assert all(os.path.isfile(files.rebuilt_pdf(b, p.id)) for p in texts)
    drawn = [
        j["params"] for j in fake_models.jobs if j["role"] == "page-build" and j["params"].get("font_fit") is not None
    ]
    with store.session() as s:
        pictured = set(s.scalars(select(Figure.page_id).join(Page).where(Page.book_id == b)))
    assert any(d["groups"]["figures"] for d in drawn) is bool(
        pictured & {p.id for p in texts}
    )  # its pictures kept (review)
    pipeline.Runner(ocr=tesseract_ocr, correct=None, run_model=None).run(pipeline.Task(b, ("rebuild",)))
    with store.session() as s:
        assert "strata-models is not set up" in s.get(Book, b).error


def test_a_rebuild_needs_read_pages_and_a_stop_in_it_is_finished_not_restarted(make_book, runner):
    b = make_book()
    runner.run(pipeline.Task(b, ("import", "detect")))
    with pytest.raises(
        pipeline.StageError, match="strata-models is not set up"
    ):  # pages never read are still set, as pictures or blanks
        runner.rebuild_one(pages_of(b)[0])
    unread = pages_of(b)[0]
    pipeline.Runner(ocr=runner.ocr, correct=None, run_model=lambda role, params, model: {}).rebuild_one(unread)
    assert (
        next(p for p in pages_of(b) if p.id == unread.id).ocr is None
    )  # still unread: its first reading guesses its kind (review)
    assert pipeline.resume_from("rebuild") == ("rebuild", "export")
    assert pipeline.resume_from("read") == ("read", "export")
    assert pipeline.resume_from("???") == ("detect", "read")


def models_answers(service):
    """strata-models' answers for the layout roles, from what each job is sent (the real page-build draws; this writes a small PDF)."""

    def page_build(params):
        ocr = params["ocr"]
        if params.get("list_lines"):
            w, h = float(ocr["width"]), float(ocr["height"])

            def k(b):  # the line's box in thousandths of the page, as the real page-build lists it
                return ",".join(
                    str(round(v))
                    for v in (b[0] * 1000 / w, b[1] * 1000 / h, (b[0] + b[2]) * 1000 / w, (b[1] + b[3]) * 1000 / h)
                )

            rows = [f"{n} b1 [{k(ln['box'])}] {ln['text']}" for n, ln in enumerate(ocr["lines"], 1)]
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


def test_a_reading_held_between_the_passes_keeps_no_image():
    # the read stage holds every page's Reading until the bulk answers come: a decoded scan in each would be gigabytes for a long book
    import dataclasses

    assert {f.name for f in dataclasses.fields(pipeline.Reading)} == {
        "png",
        "r",
        "boxes",
        "confs",
        "sure",
        "kind",
        "prompt",
        "prompt_error",
    }


def test_a_books_plain_pages_share_the_font_shortlist_of_its_first_ones(make_book, fake_models):
    """Pages laid out from their own lines are plain: the first SAMPLE ask for a shortlist, the rest are given the faces those named most."""
    from books import tesseract_ocr

    answers = models_answers(fake_models)
    fake_models.results = answers
    r = pipeline.Runner(ocr=tesseract_ocr, correct=None, reread=None, run_model=layout.models_run)
    from books import page

    lines = [f"line {i} of the plain running text of a page" for i in range(14)]
    b = make_book(scans=[page(lines) for _ in range(5)])
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    texts = [p for p in pages_of(b) if p.kind == "text"]
    assert len(texts) >= 4
    assert all(p.ocr["layout"]["model"] == layout.PLAIN for p in texts)
    assert not [
        j
        for j in fake_models.jobs
        if j["role"] == "vision-language" and j["params"].get("preset") == "page-layout-fix-v2"
    ]
    named = iter([["caslon", "bodoni"], ["caslon", "baskerville"], ["caslon", "bodoni"]])
    asked = []

    def fit(params):
        asked.append(params.get("candidates"))
        return {"face": "tinos", "blocks": [], "fonts": {}, "proposed": params.get("candidates") or next(named)}

    fake_models.results = {**answers, "font-match": fit}
    r.run(pipeline.Task(b, ("rebuild",)))
    assert asked[: pipeline.SAMPLE] == [None] * pipeline.SAMPLE
    assert all(a == ["caslon", "bodoni", "baskerville"] for a in asked[pipeline.SAMPLE :])
    kinds = [p.ocr["type"]["asked"] for p in pages_of(b) if p.kind == "text"]
    assert kinds.count(True) == pipeline.SAMPLE


def test_a_page_that_fails_both_ways_is_read_again_by_another_reader_and_kept_only_when_it_passes(
    make_book, fake_models
):
    """Every first setting lacks its words, and the rows find nothing to put right; the reader's setting is the page as Tesseract's PDF of it,
    but for one page whose reader's setting lacks them too."""
    from books import tesseract_ocr

    answers = models_answers(fake_models)
    fake_models.results = answers
    r = pipeline.Runner(ocr=tesseract_ocr, correct=None, reread=None, run_model=layout.models_run)
    b = make_book()
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    texts = [p for p in pages_of(b) if p.kind == "text" and p.ocr and p.ocr["layout"]]
    assert len(texts) > 1
    bad = texts[0].id
    draw, asked = answers["page-build"], []

    def page_build(params):
        got = draw(params)
        out = os.path.basename(params.get("out", ""))
        if params.get("font_fit") and out.endswith(".reader.pdf") and not out.startswith(f"{bad}."):
            shutil.copyfile(files.ocr_pdf(b, int(out.split(".")[0])), params["out"])
        return got

    def ocr(params):
        asked.append(params["path"])
        assert "dpi" not in params  # docTR refuses Tesseract's params
        return tesseract_ocr(params["path"], params["path"] + ".x.pdf", "eng", 300)

    fake_models.results = {**answers, "page-build": page_build, "ocr": ocr}
    r.run(pipeline.Task(b, ("rebuild",)))
    by_id = {p.id: p for p in pages_of(b)}
    assert len(asked) == len(texts)
    assert [j["model"] for j in fake_models.jobs if j["role"] == "ocr"] == [pipeline.READER] * len(texts)
    for p in texts:
        assert by_id[p.id].ocr["gate"]["passed"] is (p.id != bad)
        assert not os.path.exists(files.rebuilt_pdf(b, p.id) + ".reader.pdf")


def test_a_leaf_keeps_its_writing_on_white_and_a_cover_is_cut_to_the_book(make_book, fake_models):
    """A blank leaf with an owner's name is that name on white; a cover photographed on a dark backdrop is the book, cut from its whole scan
    (not its page crop); made so, neither is made again."""
    import cv2
    import numpy as np
    from books import tesseract_ocr

    fake_models.results = models_answers(fake_models)
    r = pipeline.Runner(ocr=tesseract_ocr, correct=None, reread=None, run_model=layout.models_run)
    b = make_book()
    r.run(pipeline.Task(b, ("import", "detect", "read")))
    leaf, cover = pages_of(b)[:2]
    name = np.full((1600, 1000, 3), (180, 215, 230), np.uint8)
    for k in range(6):  # a signature's strokes
        cv2.line(name, (300 + 40 * k, 500), (320 + 40 * k, 440), (70, 70, 80), 5)
    cv2.imwrite(files.page_png(b, leaf.id), name)
    photo = np.full((1600, 1200, 3), 25, np.uint8)
    photo[200:1400, 300:900] = (60, 90, 70)
    with store.session() as s:
        s.get(Page, leaf.id).kind = "blank"
        s.get(Page, cover.id).kind = "cover"
        s.get(Page, cover.id).angle = 0.0
        scan = s.get(Scan, cover.scan_id)
        cv2.imwrite(os.path.join(files.book_dir(b), scan.file), photo)
    fake_models.jobs.clear()
    r.run(pipeline.Task(b, ("rebuild",), (leaf.id, cover.id)))
    drawn = {
        int(os.path.basename(j["params"]["out"]).split(".")[0]): j["params"]
        for j in fake_models.jobs
        if j["role"] == "page-build" and "out" in j["params"]
    }
    (mark,) = drawn[leaf.id]["groups"]["figures"]
    assert mark["image"].endswith(f"{leaf.id}.marks.png")
    assert not drawn[leaf.id]["rules"]
    assert mark["box"][0] < 300  # where the name is on the leaf, in thousandths
    assert mark["box"][1] < 300
    cut = cv2.imread(mark["image"])
    assert np.median(cut) == 255  # on white
    assert cut.min() < 120  # the strokes dark
    (book_cut,) = drawn[cover.id]["groups"]["figures"]
    assert drawn[cover.id]["image"].endswith(f"{cover.id}.book.png")
    assert cv2.imread(drawn[cover.id]["image"]).shape[:2] == pytest.approx((1200, 600), abs=30)
    assert book_cut["box"] == [0.0, 0.0, 1000.0, 1000.0]
    marbled = np.random.default_rng(3).integers(0, 255, (160, 100, 3), dtype=np.uint8)
    cv2.imwrite(files.page_png(b, leaf.id), cv2.resize(marbled, (1000, 1600), interpolation=cv2.INTER_NEAREST))
    with store.session() as s:
        s.get(Page, leaf.id).kind = "text"  # a marbled endpaper the OCR read letters in: no type to set
        line = {"text": "AAA ARAA", "box": [100, 100, 300, 40], "words": []}
        s.get(Page, leaf.id).ocr = dict(s.get(Page, leaf.id).ocr or {}, lines=[line])
        s.get(Page, leaf.id).text = "AAA ARAA"
    fake_models.jobs.clear()
    r.run(pipeline.Task(b, ("rebuild",), (leaf.id,)))
    (pattern,) = [j["params"] for j in fake_models.jobs if j["role"] == "page-build" and "out" in j["params"]]
    assert pattern["image"] == files.page_png(b, leaf.id)  # kept within its page crop, not the whole scan (review)
    assert all(pipeline.made(p) for p in pages_of(b) if p.id in (leaf.id, cover.id))
    with store.session() as s:
        s.get(Page, cover.id).kind = "picture"  # a person says it is a picture: made again
    assert not pipeline.made(next(p for p in pages_of(b) if p.id == cover.id))
