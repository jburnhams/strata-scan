"""The work on a book, in stages, on one background thread of the server (`Runner`):

    import   the source becomes numbered scans (sources.py) and their previews
    detect   each scan's pages are found (geometry.find_pages), drawn (pages/<id>.png) and numbered in reading order
    read     each page is read by strata-models' `ocr` role (lines, words, a searchable PDF page), its pictures found (figures.py) and cut out,
             and its kind guessed (text, picture, blank, cover)
    rebuild  (only when asked) each text page is set again in matching type (layout.rebuild_page) and checked (gate.check_page): a page that
             fails is tried by other routes and, failing those, kept as set and listed to look at; each picture page is its pictures cut
             onto clean paper
    export   the book's files are written (export.py)

A stage works on the whole book or on some pages (`pages`: after a person moves a crop, only that page is drawn and read again). Hand work
is kept: detect leaves a scan alone if a person set any of its pages, read keeps a corrected text and hand-drawn pictures. One book stage
runs at a time, so two requests never write the same files; inside a stage, pages are done `settings.workers` at once (OCR waits on the
strata-models service, the pixel work in OpenCV releases the GIL). A stage's calls to the cloud models are queued ahead in bulk (ahead.py:
20 or more go through strata-models' batch API at half the price, answered within a day): `read` does every page's OCR first, then queues
their corrections and layouts; `rebuild` queues every page's line texts and second reading before it sets the first. Progress is the book's `stage`, `done` and `total`, which the web app
polls; a failure is the book's `error` and the failing page's `error`, in words, and the stage carries on with the other pages.

After the OCR, a text page is read by Tesseract again from a cleaned picture (`reread`: the eval ocr-hard's `adaptive`) and that text is
corrected against the page by a vision-language model (`settings.correct_model`, `correct`): the words change, the first reading's lines and
boxes stay, and the result keeps both texts (`ocr["corrected"]`). Its layout is read too (`settings.layout_model`, `layout.read_layout`:
`ocr["layout"]`), which the Markdown and the rebuild follow. A failed or implausible correction
(far shorter or longer than what it corrected) leaves Tesseract's text, and the page says so in `ocr["corrected"]["error"]`.

The OCR and correction functions are parameters (`Runner(ocr=..., correct=...)`) only so the strata-models service can be stood in for: by
default they are the client."""

import json
import logging
import os
import threading
from collections import Counter, deque
from collections.abc import Callable, Generator, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

import cv2
import numpy as np
from sqlalchemy import delete, func, select, update
from strata_python.clients import models as sm

from stratascan import ahead, export, figures, files, gate, geometry, layout, marks, rows, settings, sources, store
from stratascan.db.models import Book, Figure, Page, Scan

log = logging.getLogger("stratascan")
APP = "strata-scan"
STAGES = ("import", "detect", "read", "export")  # a whole book
ALL_STAGES = (
    "import",
    "detect",
    "read",
    "rebuild",
    "export",
)  # with the one only done when asked (minutes and cents a page)
# (page png, pdf to write, languages, the scan's dpi) -> the ocr role's answer. The dpi matters twice: Tesseract sizes type by it, and the
# PDF page it writes is the picture's pixels at that dpi (without it a 500 dpi page came out as a 1 m tall PDF page).
OcrFn = Callable[[str, str, str, int], dict[str, Any]]


def models_ocr(path: str, pdf: str, lang: str, dpi: int) -> dict[str, Any]:
    try:
        return dict(sm.run("ocr", {"path": path, "pdf": pdf, "lang": lang, "dpi": dpi}, app=APP))
    except sm.Unavailable as e:
        raise StageError(f"strata-models is not running ({e}); start it, then read the pages again") from e
    except sm.JobFailed as e:
        raise StageError(f"strata-models could not read the page: {e}") from e


# (page png, languages, dpi) -> the ocr role's answer for the page cleaned first. Only its text is used: it is the one corrected (ocr-hard,
# 2026-11-24: Tesseract on the adaptively thresholded page, then Haiku, 0.27 % of characters wrong on ten hard pages; plain Tesseract then
# Haiku 0.88 %, then qwen3.5-9b 3.7 %, alone 23 %).
RereadFn = Callable[[str, str, int], dict[str, Any]]
CLEAN = "adaptive"


def models_reread(path: str, lang: str, dpi: int) -> dict[str, Any]:
    try:
        return dict(sm.run("ocr", {"path": path, "lang": lang, "dpi": dpi, "clean": CLEAN}, app=APP))
    except (sm.Unavailable, sm.JobFailed) as e:
        raise StageError(f"strata-models could not read the cleaned page: {e}") from e


# (page png, Tesseract's text, model) -> the corrected text. The preset is strata-models' ocr-correct-v2, the one its ocr-hard eval measured.
CorrectFn = Callable[[str, str, str], str]


def correct_params(path: str, text: str, model: str) -> dict[str, Any]:
    params: dict[str, Any] = {"image": path, "prompt": text, "system_preset": "ocr-correct-v2", "max_tokens": 4096}
    if not model.endswith("-api"):  # the local models; a cloud model runs as the eval ran it
        params["temperature"] = 0.0
    return params


def models_correct(path: str, text: str, model: str) -> str:
    try:
        r = sm.run("vision-language", correct_params(path, text, model), app=APP, model=model)
    except sm.Unavailable as e:
        raise StageError(f"strata-models is not running ({e})") from e
    except sm.JobFailed as e:
        raise StageError(f"strata-models could not correct the page: {e}") from e
    return str(r.get("text") or "")


def plausible(before: str, after: str) -> bool:
    """Is a correction a correction? It fixes letters and words, so its length stays near the text's: far shorter means it stopped or left
    lines out, far longer that it added words or described the page."""
    a, b = len(before.strip()), len(after.strip())
    return b > 0 and 0.7 * a <= b <= 1.3 * a + 20


READER = "doctr-haiku-fix"  # the last route's reader: docTR's word boxes, Claude Haiku's text (strata-models, eval ocr-lines)
SAMPLE = 3  # plain pages of a book whose font shortlist is asked for before the rest share theirs
SHORTLIST = 4  # faces in a shared shortlist: as many as the proposer names for a page


class StageError(RuntimeError):
    """A failure to show the person, in words."""


@dataclass(frozen=True)
class Reading:
    """A page as the read stage's first pass leaves it: its OCR, what was found in it, and the text to correct (`prompt`, None when there
    is none to correct; `prompt_error` when the cleaned reading failed). Not the decoded image: the stage holds every page's reading
    until the bulk answers come, and a few hundred full-size scans would not fit in memory, so the second pass reads it again."""

    png: str
    r: dict[str, Any]
    boxes: list[tuple[int, int, int, int]]
    confs: list[float]
    sure: int
    kind: str
    prompt: str | None
    prompt_error: str | None


@dataclass(frozen=True)
class Task:
    book_id: int
    stages: tuple[str, ...]
    pages: tuple[int, ...] | None = None


def read_image(path: str) -> geometry.Image:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise StageError(f"cannot read the picture {path}")
    return np.asarray(img, dtype=np.uint8)


def write_jpeg(path: str, img: geometry.Image, long_side: int) -> None:
    h, w = img.shape[:2]
    s = min(1.0, long_side / max(h, w))
    small = (
        cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA) if s < 1 else img
    )
    cv2.imwrite(path, small, [cv2.IMWRITE_JPEG_QUALITY, 85])


class Runner:
    def __init__(
        self,
        ocr: OcrFn = models_ocr,
        correct: CorrectFn | None = models_correct,
        reread: RereadFn | None = models_reread,
        run_model: layout.RunFn | None = layout.models_run,
    ) -> None:
        self.ocr = ocr
        self.correct: CorrectFn | None = correct
        self.reread = reread
        self.run_model: layout.RunFn | None = run_model  # None: no layout (tests)
        self._q: deque[Task] = deque()
        self._cv = threading.Condition()
        self._busy = False
        self._stop = False
        self._thread: threading.Thread | None = None
        self._paper: dict[int, float | None] = {}  # each book's paper colour (paper_hue), once per run of the server

    # -- the queue ---------------------------------------------------------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="stratascan-runner", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        if self._thread is not None:
            self._thread.join(30)
            self._thread = None

    def submit(self, book_id: int, stages: Sequence[str], pages: Iterable[int] | None = None) -> None:
        bad = [s for s in stages if s not in ALL_STAGES]
        if bad:
            raise ValueError(f"no stage {bad[0]!r} (stages: {', '.join(ALL_STAGES)})")
        t = Task(book_id, tuple(stages), None if pages is None else tuple(pages))
        with store.session() as s:  # shows as waiting at once, before the thread picks it up
            s.execute(
                update(Book)
                .where(Book.id == book_id, Book.stage == "idle")
                .values(stage=t.stages[0], done=0, total=0, error=None)
            )
        with self._cv:
            self._q.append(t)
            self._cv.notify_all()

    def resume(self) -> None:
        """At start: books left mid-stage by a stop are queued again from the stage they were in."""
        with store.session() as s:
            left = list(s.execute(select(Book.id, Book.stage).where(Book.stage != "idle")).all())
        for book_id, stage in left:
            with self._cv:
                self._q.append(Task(book_id, resume_from(stage)))
                self._cv.notify_all()

    def idle(self) -> bool:
        with self._cv:
            return not self._q and not self._busy

    def wait_idle(self, timeout: float = 120) -> bool:
        """Block until nothing is queued or running (tests and the CLI)."""
        with self._cv:
            return self._cv.wait_for(lambda: not self._q and not self._busy, timeout)

    def _loop(self) -> None:
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._stop or bool(self._q))
                if self._stop:
                    return
                task = self._q.popleft()
                self._busy = True
            try:
                self.run(task)
            except Exception:  # a bug in a stage must not kill the thread; the book shows the error
                log.exception("book %s: %s failed", task.book_id, task.stages)
            finally:
                with self._cv:
                    self._busy = False
                    self._cv.notify_all()

    # -- the stages --------------------------------------------------------------------------------------------------------------------

    def run(self, task: Task) -> None:
        """Run a task's stages in this thread, in order; stop at the first that fails as a whole. The book's error is cleared once, at the
        start: a stage that fails for some pages says so, and a later stage that succeeds (an export) must not hide it."""
        self._progress(task.book_id, error=None)
        scans = None
        if (
            task.pages is not None
        ):  # detect replaces a scan's pages with new ids, so the task follows the scans, not the page ids
            with store.session() as s:
                scans = set(s.scalars(select(Page.scan_id).where(Page.id.in_(task.pages))))
        for stage in task.stages:
            self._progress(task.book_id, stage=stage, done=0, total=0)
            pages = task.pages
            if scans is not None:
                with store.session() as s:
                    pages = tuple(s.scalars(select(Page.id).where(Page.scan_id.in_(scans)))) or task.pages
            try:
                getattr(self, f"stage_{stage}")(task.book_id, pages)
            except (StageError, sources.SourceError) as e:
                self._progress(task.book_id, stage="idle", error=str(e))
                return
            except Exception as e:
                self._progress(task.book_id, stage="idle", error=f"{stage} failed: {e}")
                raise
        with store.session() as s:
            s.execute(update(Book).where(Book.id == task.book_id).values(stage="idle"))

    def _progress(self, book_id: int, **values: object) -> None:
        with store.session() as s:
            s.execute(update(Book).where(Book.id == book_id).values(**values))

    def _each(
        self, book_id: int, items: list[Any], work: Callable[[Any], None], at_once: int | None = None
    ) -> list[str]:
        """`work` on every item, `settings.workers` (or `at_once`) at once, counting progress; the failures, in words."""
        errors: list[str] = []
        self._progress(book_id, done=0, total=len(items))
        done = 0
        with ThreadPoolExecutor(max_workers=at_once or settings.workers()) as pool:
            for err in pool.map(partial(_catch, work), items):
                done += 1
                if err:
                    errors.append(err)
                self._progress(book_id, done=done)
        return errors

    @contextmanager
    def queued_ahead(self, calls: list[ahead.Call]) -> Generator[None]:
        """While a stage runs: its planned cloud calls queued in bulk (ahead.py; 20 or more on a Claude model go through its batch API at
        half the price) and answered from there when a page makes them. One stage runs at a time, so swapping the run functions is safe."""
        if not calls:
            yield
            return
        bulk = ahead.Ahead()
        bulk.send(calls)
        run, correct = self.run_model, self.correct
        if run is not None:
            self.run_model = bulk.wrap(
                run, lambda role, e: layout.LayoutError(f"strata-models could not do it ({role}): {e}")
            )
        if correct is not None:
            plain = correct

            def at_once(role: str, params: dict[str, Any], model: str | None) -> dict[str, Any]:
                return {"text": plain(str(params["image"]), str(params["prompt"]), str(model))}

            answered = bulk.wrap(at_once, lambda role, e: StageError(f"strata-models could not correct the page: {e}"))

            def queued(png: str, text: str, model: str) -> str:
                return str(answered("vision-language", correct_params(png, text, model), model).get("text") or "")

            self.correct = queued
        try:
            yield
        finally:
            self.run_model, self.correct = run, correct

    def read_calls(self, pages: list[Page], readings: dict[int, "Reading"]) -> list[ahead.Call]:
        """The read stage's cloud calls, known once every page has its OCR: each text page's correction and layout. Only when they are the
        client's own (a stand-in in a test is called as it is)."""
        calls: list[ahead.Call] = []
        fix, lay = settings.correct_model(), settings.layout_model()
        for p in pages:
            rd = readings[p.id]
            if self.correct is models_correct and fix is not None and rd.prompt:
                calls.append(("vision-language", correct_params(rd.png, rd.prompt, fix), fix))
            if (
                self.run_model is layout.models_run
                and lay is not None
                and rd.kind == "text"
                and clean_text(rd.r, rd.sure, rd.kind)
            ):
                try:
                    context = layout.numbered(rd.r, layout.models_run)
                except layout.LayoutError:
                    continue
                if context and (rd.boxes or not layout.plain_groups(context)):  # a plain page asks no layout model
                    calls.append(("vision-language", layout.layout_params(rd.png, context), lay))
        return calls

    def rebuild_calls(self, pages: list[Page]) -> list[ahead.Call]:
        """The rebuild stage's cloud calls, known before any page is set: each page's line texts put right and its second reading. A page
        whose plan fails is left to make its calls when it is set."""
        calls: list[ahead.Call] = []
        if self.run_model is not layout.models_run:
            return calls
        for p in pages:
            png = files.page_png(p.book_id, p.id)
            if p.text_edited or not os.path.isfile(png):
                continue
            try:
                _, ocr = self.tidied(p, png)
                if not (cast("dict[str, Any]", ocr.get("layout") or {})).get("groups"):
                    continue
                run = layout.models_run
                context = layout.numbered(layout.settled(ocr, p.ocr or {}, run), run)
            except (layout.LayoutError, StageError) as e:
                log.warning("page %s: its calls are not queued ahead: %s", p.id, e)
                continue
            calls.append(("vision-language", layout.text_params(png, context), layout.TEXT_MODEL))
            calls.append(("vision-language", layout.read_params(png), layout.TEXT_MODEL))
        return calls

    def stage_import(self, book_id: int, pages: tuple[int, ...] | None = None) -> None:
        with store.session() as s:
            book = s.get(Book, book_id)
            if book is None:
                return
            source = book.source
            s.execute(delete(Scan).where(Scan.book_id == book_id))
        files.remove_book(book_id)
        scans = sources.import_scans(
            source, book_id, settings.max_dpi(), lambda d, t: self._progress(book_id, done=d, total=t)
        )
        with store.session() as s:
            rows = [
                Scan(book_id=book_id, position=x.position, file=x.file, width=x.width, height=x.height, dpi=x.dpi)
                for x in scans
            ]
            s.add_all(rows)
            s.flush()
            made = [(r.id, r.file) for r in rows]
        self._each(
            book_id,
            made,
            lambda r: write_jpeg(
                files.preview(book_id, "scan", r[0]),
                read_image(os.path.join(files.book_dir(book_id), r[1])),
                files.PREVIEW,
            ),
        )

    def stage_detect(self, book_id: int, pages: tuple[int, ...] | None = None) -> None:
        with store.session() as s:
            scans = list(s.scalars(select(Scan).where(Scan.book_id == book_id).order_by(Scan.position)))
            # a scan with any of a person's work on its pages is left alone: a cut, typed text or a drawn picture (re-detecting
            # would delete the pages, and the text and pictures with them)
            mine = (Page.hand | Page.text_edited) | Page.id.in_(select(Figure.page_id).where(Figure.hand))
            hand = set(s.scalars(select(Page.scan_id).where(Page.book_id == book_id, mine)))
            if pages is not None:  # only the scans of these pages
                wanted = set(s.scalars(select(Page.scan_id).where(Page.id.in_(pages))))
                scans = [x for x in scans if x.id in wanted]
        if not scans:
            raise StageError("the book has no scans: import it first")
        last = max(x.position for x in scans)

        def detect(scan: Scan) -> None:
            if scan.id in hand:
                return
            img = read_image(os.path.join(files.book_dir(book_id), scan.file))
            found = geometry.find_pages(img)
            with store.session() as s:
                old = list(s.scalars(select(Page.id).where(Page.scan_id == scan.id)))
                s.execute(delete(Page).where(Page.scan_id == scan.id))
                for pid in old:
                    files.remove(
                        files.page_png(book_id, pid),
                        files.preview(book_id, "page", pid),
                        files.preview(book_id, "thumb", pid),
                        files.ocr_pdf(book_id, pid),
                        files.rebuilt_pdf(book_id, pid),
                    )
                for i, g in enumerate(found):
                    cover = g.confidence <= 0.2 and (scan.position <= 2 or scan.position >= last - 1)
                    x, y, w, h = g.crop
                    s.add(
                        Page(
                            book_id=book_id,
                            scan_id=scan.id,
                            position=scan.position * 10 + i,
                            side=g.side,
                            angle=g.angle,
                            crop_x=x,
                            crop_y=y,
                            crop_w=w,
                            crop_h=h,
                            confidence=g.confidence,
                            kind="cover" if cover else "text",
                        )
                    )

        errors = self._each(book_id, scans, detect)
        renumber(book_id)
        with store.session() as s:
            q = select(Page).where(Page.book_id == book_id, Page.rendered.is_(False))
            todo = list(s.scalars(q))
        errors += self._each(book_id, todo, lambda p: render(p))
        if errors:
            self._progress(book_id, error=f"{len(errors)} scan(s) failed: {errors[0]}")

    def stage_read(self, book_id: int, pages: tuple[int, ...] | None = None) -> None:
        with store.session() as s:
            book = s.get(Book, book_id)
            lang = book.lang if book else "eng"
            q = select(Page).where(Page.book_id == book_id).order_by(Page.position)
            if pages is not None:
                q = q.where(Page.id.in_(pages))
            todo = list(s.scalars(q))
        if not todo:
            raise StageError("the book has no pages: find them first")
        # two passes: the OCR of every page, then its cloud calls (correction, layout) queued in bulk and each page finished as they come
        readings: dict[int, Reading] = {}

        def first(p: Page) -> None:
            readings[p.id] = self.first_read(p, lang)

        errors = self._each(book_id, todo, first)
        read = [p for p in todo if p.id in readings]
        with self.queued_ahead(self.read_calls(read, readings)):
            errors += self._each(book_id, read, lambda p: self.finish_read(p, readings.pop(p.id)))
        if errors:
            self._progress(book_id, error=f"{len(errors)} of {len(todo)} pages could not be read: {errors[0]}")

    def read_page(self, page: Page, lang: str) -> None:
        """Read one page: its OCR, then its correction and layout (the stage does every page's first, then queues their cloud calls)."""
        self.finish_read(page, self.first_read(page, lang))

    def first_read(self, page: Page, lang: str) -> Reading:
        if not page.rendered or not os.path.isfile(files.page_png(page.book_id, page.id)):
            render(page)
        png = files.page_png(page.book_id, page.id)
        try:
            r = self.ocr(png, files.ocr_pdf(page.book_id, page.id), lang, scan_dpi(page))
        except StageError as e:
            with store.session() as s:
                s.execute(update(Page).where(Page.id == page.id).values(error=str(e)))
            raise
        img = read_image(png)
        words = [
            ((int(w["box"][0]), int(w["box"][1]), int(w["box"][2]), int(w["box"][3])), float(w["conf"]))
            for ln in r.get("lines", [])
            for w in ln.get("words", [])
        ]
        boxes = [figures.pad_box(b, img.shape[1], img.shape[0]) for b in figures.find_figures(img, words)]
        confs = [c for _, c in words]
        sure = sum(1 for c in confs if c >= figures.WORD_CONF)
        kind = page.kind
        if (
            page.ocr is None and kind == "text"
        ):  # the first read guesses the kind; a person's or an earlier read's stays
            area = sum(w * h for _, _, w, h in boxes) / float(img.shape[0] * img.shape[1])
            kind = "picture" if area > 0.3 and sure < 25 else "blank" if not boxes and sure < 3 else "text"
        prompt, why = self.correction_prompt(page, png, r, sure, kind, lang)
        return Reading(png, r, boxes, confs, sure, kind, prompt, why)

    def finish_read(self, page: Page, rd: Reading) -> None:
        png, boxes, confs, sure, kind = rd.png, rd.boxes, rd.confs, rd.sure, rd.kind
        r = dict(rd.r, corrected=self.correct_page(rd), layout=self.layout_page(page, png, rd.r, sure, kind, boxes))
        files.remove(files.rebuilt_pdf(page.book_id, page.id))  # set from the reading this one replaces
        with store.session() as s:
            p = s.get(Page, page.id)
            if p is None:
                return
            if p.ocr is None and p.kind == "text":  # as guessed above, unless a person set the kind meanwhile
                p.kind = kind
            p.ocr, p.ocr_model, p.error = r, str(r.get("model") or r.get("engine") or "ocr"), None
            p.ocr_conf = round(sum(confs) / len(confs), 1) if confs else None
            if not p.text_edited:
                fixed = r["corrected"]
                p.text = (
                    fixed["text"] if fixed and fixed.get("text") and p.kind == "text" else clean_text(r, sure, p.kind)
                )
            lines = (p.text or "").splitlines()
            if p.label is None and p.kind == "text" and lines and export.is_running_head(lines[0], len(lines)):
                p.label = export.page_number(lines[0])
            old = list(s.scalars(select(Figure).where(Figure.page_id == p.id, Figure.hand.is_(False))))
            for f in old:
                files.remove(files.figure_png(p.book_id, f.id))
                s.delete(f)
            if not any(f.hand for f in s.scalars(select(Figure).where(Figure.page_id == p.id))):
                for x, y, w, h in boxes:
                    s.add(Figure(page_id=p.id, x=x, y=y, w=w, h=h))
            s.flush()
            cut = [(f.id, f.x, f.y, f.w, f.h) for f in s.scalars(select(Figure).where(Figure.page_id == p.id))]
        if cut:  # the image is read again here, not kept from the first pass (see Reading)
            img = read_image(png)
            for fid, x, y, w, h in cut:
                cv2.imwrite(files.figure_png(page.book_id, fid), img[y : y + h, x : x + w])

    def correction_prompt(
        self, page: Page, png: str, r: dict[str, Any], sure: int, kind: str, lang: str
    ) -> tuple[str | None, str | None]:
        """(the text to correct, why there is none): (None, None) when there is no correction to do: correction off, a page a person typed, or
        one with no text or that is not a text page (a cover, a picture, a blank)."""
        model = settings.correct_model()
        text = clean_text(r, sure, kind)
        if self.correct is None or model is None or page.text_edited or kind != "text" or not text:
            return None, None
        try:
            return self.cleaned_text(png, lang, scan_dpi(page), kind, text), None
        except StageError as e:
            return None, str(e)

    def correct_page(self, rd: Reading) -> dict[str, Any] | None:
        """The correction of a page's OCR text, as {model, text, lines: the OCR lines it corrected} (or {model, error}), or None when there is
        none to do (`correction_prompt`)."""
        model = settings.correct_model()
        if model is None or self.correct is None or (rd.prompt is None and rd.prompt_error is None):
            return None
        if rd.prompt is None:
            log.warning("correction failed: %s", rd.prompt_error)
            return {"model": model, "error": rd.prompt_error}
        try:
            fixed = self.correct(rd.png, rd.prompt, model).strip()
        except StageError as e:
            log.warning("correction failed: %s", e)
            return {"model": model, "error": str(e)}
        if not plausible(rd.prompt, fixed):
            return {
                "model": model,
                "error": f"the correction was {len(fixed)} characters for {len(rd.prompt)}: kept the OCR text",
            }
        # the OCR lines it corrected, so the export can put each corrected line where its OCR line was (export.page_markdown)
        return {"model": model, "text": fixed, "lines": kept_lines(rd.r, rd.sure, rd.kind)}

    def cleaned_text(self, png: str, lang: str, dpi: int, kind: str, text: str) -> str:
        """The text to correct: Tesseract's reading of the cleaned page, unless there is none, or cleaning lost much of the page."""
        if self.reread is None:
            return text
        r = self.reread(png, lang, dpi)
        sure = sum(1 for ln in r.get("lines", []) for w in ln.get("words", []) if float(w["conf"]) >= figures.WORD_CONF)
        cleaned = clean_text(r, sure, kind)
        return cleaned if len(cleaned) >= 0.7 * len(text) else text

    def layout_page(
        self,
        page: Page,
        png: str,
        r: dict[str, Any],
        sure: int,
        kind: str,
        pictures: list[tuple[int, int, int, int]] | None = None,
    ) -> dict[str, Any] | None:
        """The page's layout (layout.read_layout), or {model, error}, or None when there is none to read: layout off, or not a text page. A
        page that failed here keeps its text: the Markdown falls back to Tesseract's blocks. A plain page with no pictures is laid out from
        its own lines (layout.plain_groups), with no model asked."""
        model = settings.layout_model()
        if self.run_model is None or model is None or kind != "text" or not clean_text(r, sure, kind):
            return None
        try:
            groups = None if pictures else layout.plain_groups(layout.numbered(r, self.run_model))
            return layout.read_layout(png, r, model, scan_dpi(page), self.run_model, groups)
        except layout.LayoutError as e:
            log.warning("page %s: layout failed: %s", page.id, e)
            return {"model": model, "error": str(e)}

    def stage_rebuild(self, book_id: int, pages: tuple[int, ...] | None = None) -> None:
        with store.session() as s:
            # every page but a skipped one: the only scans a finished book keeps are its pictures and patterns (Jonathan, 2026-11-26)
            q = select(Page).where(Page.book_id == book_id, Page.kind != "skip")
            if pages is not None:
                q = q.where(Page.id.in_(pages))
            todo = list(s.scalars(q.order_by(Page.position)))
        if pages is None:
            # a page already made as it would be made now is kept: its type fit cost minutes and its layout cents (Jonathan, 2026-11-26:
            # "we should be smart enough to not redo stuff"). Pages named are made again whatever they hold.
            todo = [p for p in todo if not made(p)]
            if not todo:
                return
        # the worst read first (stable, so reading order among equals): whoever looks while it runs sees the pages most likely to fail the gate
        todo.sort(key=lambda p: p.ocr_conf if p.ocr_conf is not None else 100.0)
        if not todo:
            raise StageError("the book has no pages to set again: find them first")
        # one at a time: a type fit is minutes of CPU and the heaviest job strata-models runs for this app (fourteen queued pages once ran the
        # service out of memory, 2026-11-24)
        with self.queued_ahead(
            self.rebuild_calls(todo)
        ):  # the cloud calls of every page in bulk; the type fits still one at a time
            errors = self._each(book_id, todo, self.rebuild_one, at_once=1)
        if errors:
            self._progress(book_id, error=f"{len(errors)} of {len(todo)} pages could not be set again: {errors[0]}")

    def rebuild_one(self, page: Page) -> None:
        if self.run_model is None:
            raise StageError("strata-models is not set up")
        if not typeset(page):
            self.rebuild_picture(page)
            return
        png = files.page_png(page.book_id, page.id)
        if not os.path.isfile(png):
            render(page)
        out = files.rebuilt_pdf(page.book_id, page.id)
        dpi = scan_dpi(page)
        gray, ocr = self.tidied(page, png)
        was = page.ocr or {}
        if not cast("dict[str, Any]", ocr.get("layout") or {}).get("groups"):
            # its layout could not be read (the model's answer was not one): laid out from its own lines, as one block when not plain, so a
            # text page is still set in type
            try:
                context = layout.numbered(ocr, self.run_model)
                one = {"blocks": [{"lines": [n for n, _, _ in layout.numbered_lines(context)], "role": "body"}]}
                groups = layout.plain_groups(context) or one
                # its pictures, as the read found them or a person drew them: a layout model would have named them (review)
                groups = dict(groups, figures=self.figures_in_thousandths(page, gray.shape))
                ocr = dict(ocr, layout=layout.read_layout(png, ocr, layout.PLAIN, dpi, self.run_model, groups))
                was = ocr
            except layout.LayoutError as e:
                raise StageError(str(e)) from e
        plain = cast("dict[str, Any]", ocr.get("layout") or {}).get("model") == layout.PLAIN
        faces = self.book_faces(page.book_id) if plain else None
        try:
            used = self.set_in_type(page, ocr, png, out, dpi, was, faces)
        except layout.LayoutError as e:
            files.remove(out)
            raise StageError(str(e)) from e
        again = self.second_reading(page, png)
        verdict = self.judge(page, ocr, png, out, dpi, again)
        fixed, also = 0, ()
        if not verdict.passed and not page.text_edited:
            verdict, fixed, also = self.set_from_rows(page, ocr, gray, png, out, dpi, again, verdict)
            if not verdict.passed:
                verdict, also = self.set_from_reader(page, png, out, dpi, again, verdict, also)
        with store.session() as s:
            p = s.get(Page, page.id)
            if p is not None and p.ocr is not None:
                record = {
                    **verdict.record(),
                    "by": "text" if again is None else "both",
                    "lines_put_right": fixed,
                    "from_rows": list(also),
                }
                # a new dict: SQLAlchemy does not see a JSON column change in place. `type`: the font shortlist this page was set with
                kept = {"faces": used, "plain": plain, "asked": faces is None}
                p.ocr = dict(p.ocr, gate=dict(record, kind=page.kind), type=kept)

    def figures_in_thousandths(self, page: Page, shape: tuple[int, ...]) -> list[dict[str, Any]]:
        """The page's pictures as a layout names them: boxes [x0, y0, x1, y1] in thousandths of the page."""
        high, wide = shape[0], shape[1]
        with store.session() as s:
            figs = list(s.scalars(select(Figure).where(Figure.page_id == page.id)))
        return [
            {
                "box": [1000 * f.x / wide, 1000 * f.y / high, 1000 * (f.x + f.w) / wide, 1000 * (f.y + f.h) / high],
                "kind": "figure",
            }
            for f in figs
        ]

    def rebuild_picture(self, page: Page) -> None:
        """A page with no text to set (`typeset`). A cover is the book photographed: kept whole, trimmed to the book (marks.book_box). Its
        pictures cut from the scan onto clean paper. Otherwise what is on its paper, lifted onto white (marks.lift: handwriting, a bookplate,
        a shelf mark; Jonathan, 2026-11-26: err on the side of keeping content), or kept whole when that is most of the page (a pattern:
        marbled paper), or a true blank when there is nothing (layout.picture_page). No gate: no text to check."""
        png = files.page_png(page.book_id, page.id)
        if not os.path.isfile(png):
            render(page)
        with store.session() as s:
            boxes = [(f.x, f.y, f.w, f.h) for f in s.scalars(select(Figure).where(Figure.page_id == page.id))]
        crops = os.path.dirname(files.path(page.book_id, "crops", "x"))
        os.makedirs(crops, exist_ok=True)
        out = files.rebuilt_pdf(page.book_id, page.id)
        high, wide = read_image(png).shape[:2]
        made: dict[str, Any] = {}
        if page.kind == "blank":
            boxes = []  # what the page finder saw on a blank page is show-through and specks; a mark on it is lifted below
        if page.kind == "cover" or (not boxes and marks.dark(png)):
            made["whole"] = True  # the book photographed: a cover, its spine, its edges
        elif not boxes:
            lifted = marks.lift(png, self.paper_hue(page.book_id))
            if lifted.share > marks.PATTERN:
                made["whole"] = True
            elif lifted.box is not None:
                cut = marks.save(lifted, os.path.join(crops, f"{page.id}.marks.png"))
                boxes, made["marks"] = [lifted.box], cut
        if made.get("whole"):
            book = self.book_in(page, os.path.join(crops, f"{page.id}.book.png"))
            if book is not None:  # the page as the book photographed, whatever its crop took in
                png = book
                high, wide = read_image(png).shape[:2]
            boxes = [(0, 0, wide, high)]
        try:
            run = self.run_model or layout.models_run
            images = [made["marks"]] if "marks" in made else None
            layout.picture_page(
                png,
                boxes,
                out,
                scan_dpi(page),
                run,
                crops,
                images=images,
                rules="marks" not in made and not made.get("whole"),
                whole=bool(made.get("whole")),
            )
        except layout.LayoutError as e:
            files.remove(out)
            raise StageError(str(e)) from e
        verdict: dict[str, Any] = {
            "passed": True,
            "reasons": [],
            "picture": bool(boxes),
            "whole": bool(made.get("whole")),
            "marks": "marks" in made,
            "kind": page.kind,
            "way": PICTURES,
        }
        with open(out + ".json", "w", encoding="utf-8") as f:  # how it was made, read or not (made)
            json.dump(verdict, f)
        with store.session() as s:
            p = s.get(Page, page.id)
            if (
                p is not None and p.ocr is not None
            ):  # a page never read stays unread: its first reading guesses its kind (review)
                p.ocr = dict(p.ocr, gate=verdict)

    def book_in(self, page: Page, out: str) -> str | None:
        """The book cut from the page's whole scan (turned by its angle), trimmed of the backdrop it lies on (marks.book_box), written to
        `out`; None when the scan has no plain backdrop round it. The whole scan, not the page's crop: a crop found for a leaf can cut into
        a photograph of the spine or the edges, or take in all of the backdrop."""
        with store.session() as s:
            scan = s.get(Scan, page.scan_id)
            src = os.path.join(files.book_dir(page.book_id), scan.file) if scan is not None else None
        if src is None or not os.path.isfile(src):
            return None
        scan_img = read_image(src)
        behind = marks.backdrop(scan_img)
        if behind is None:
            return None
        fill = (
            int(behind[0]),
            int(behind[1]),
            int(behind[2]),
        )  # the corners a turn opens filled with the backdrop, not white
        whole = geometry.rotate(scan_img, page.angle, fill)
        box = marks.book_box(whole, behind)
        if box is None:
            return None
        x, y, w, h = box
        cv2.imwrite(out, whole[y : y + h, x : x + w])
        return out

    def paper_hue(self, book_id: int) -> float | None:
        """The book's paper colour (marks.paper_hue), from its fullest text pages: mostly paper, as no blank page is sure to be."""
        if book_id not in self._paper:
            with store.session() as s:
                q = (
                    select(Page.id)
                    .where(Page.book_id == book_id, Page.kind == "text")
                    .order_by(func.length(Page.text).desc())
                    .limit(5)
                )
                ids = list(s.scalars(q))
            self._paper[book_id] = marks.paper_hue(files.page_png(book_id, i) for i in ids)
        return self._paper[book_id]

    def tidied(self, page: Page, png: str) -> tuple[gate.Gray, dict[str, Any]]:
        """(the page in grey, its OCR tidied by its rows of ink: rows.tidy), as it is set."""
        img = np.asarray(read_image(png), dtype=np.uint8)
        gray = np.asarray(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
        return gray, rows.tidy(page.ocr or {}, gray, scan_dpi(page))

    def set_in_type(
        self,
        page: Page,
        ocr: dict[str, Any],
        png: str,
        out: str,
        dpi: int,
        was: dict[str, Any] | None = None,
        faces: list[str] | None = None,
    ) -> list[str]:
        if self.run_model is None:
            raise layout.LayoutError("strata-models is not set up")
        typed = (page.text or "") if page.text_edited else None
        return layout.rebuild_page(png, ocr, out, dpi, typed, self.run_model, page.text, was, faces)

    def book_faces(self, book_id: int) -> list[str] | None:
        """The font shortlist for a plain page of the book: the faces most often proposed for its plain pages, once SAMPLE of them have had
        one proposed. None (ask for one) before that. A book's body type is one face, so asking for each page paid for the same answer."""
        with store.session() as s:
            q = select(Page.ocr).where(Page.book_id == book_id, Page.kind == "text", Page.ocr.is_not(None))
            told: list[list[str]] = []
            for ocr in s.scalars(q):
                t = cast("dict[str, Any]", (ocr or {}).get("type") or {})
                if t.get("plain") and t.get("asked") and t.get("faces"):
                    told.append([str(f) for f in cast("list[Any]", t["faces"])])
        if len(told) < SAMPLE:
            return None
        votes = Counter(f for faces in told for f in faces)
        return [f for f, _ in votes.most_common(SHORTLIST)]

    def second_reading(self, page: Page, png: str) -> str | None:
        """The page read again by another route, to check its words by; None for a person's text (the one to hold the page to) or none to be had."""
        if page.text_edited or self.run_model is None:
            return None
        try:
            got = layout.read_again(png, self.run_model)
        except layout.LayoutError as e:
            log.warning("page %s: no second reading to check by: %s", page.id, e)
            return None
        return got if plausible(page.text or "", got) else None  # a refusal would fail the page for nothing

    def judge(self, page: Page, ocr: dict[str, Any], png: str, out: str, dpi: int, again: str | None) -> gate.Verdict:
        blocks = cast("list[dict[str, Any]]", cast("dict[str, Any]", ocr.get("layout") or {}).get("blocks") or [])
        return gate.check_page(out, png, page.text or "", blocks, dpi, again)

    def set_from_rows(
        self,
        page: Page,
        ocr: dict[str, Any],
        gray: gate.Gray,
        png: str,
        out: str,
        dpi: int,
        again: str | None,
        first: gate.Verdict,
    ) -> tuple[gate.Verdict, int, tuple[str, ...]]:
        """(verdict, lines put right, why it failed even so) of a page that failed, set again from its OCR put right by its rows (rows.repair), with the layout read for
        those lines. Kept only when it passes: a page the OCR read well can come out worse, and the first setting stands either way."""
        fixed, n = rows.repair(ocr, gray, page.text or "", dpi)
        model = settings.layout_model()
        if not n or model is None or self.run_model is None:
            return first, 0, ()
        trial = out + ".rows.pdf"
        try:
            laid = layout.read_layout(png, fixed, model, dpi, self.run_model)
            laid = layout.with_left_out(laid, layout.numbered(fixed, self.run_model), fixed)
            fixed = dict(fixed, layout=layout.with_pictures(laid, fixed.get("pictures") or [], gray.shape))
            self.set_in_type(page, fixed, png, trial, dpi)
            verdict = self.judge(page, fixed, png, trial, dpi, again)
        except layout.LayoutError as e:
            log.warning("page %s: not set again from its rows: %s", page.id, e)
            return first, 0, (str(e),)
        else:
            if not verdict.passed:
                return first, 0, verdict.reasons
            os.replace(trial, out)
            return verdict, n, ()
        finally:
            files.remove(trial)

    def set_from_reader(
        self,
        page: Page,
        png: str,
        out: str,
        dpi: int,
        again: str | None,
        first: gate.Verdict,
        why: tuple[str, ...],
    ) -> tuple[gate.Verdict, tuple[str, ...]]:
        """(verdict, why it failed even so) of a page that failed both ways, set again from another reader's lines (READER: docTR's boxes with
        Claude's text, which reads through a stain that Tesseract reads as junk), with a layout read for them. Kept only when it passes."""
        model = settings.layout_model()
        if model is None or self.run_model is None:
            return first, why
        trial = out + ".reader.pdf"
        try:
            read = dict(self.run_model("ocr", {"path": png}, READER))  # docTR takes no dpi
            laid = layout.read_layout(png, read, model, dpi, self.run_model)
            read = dict(read, layout=laid)
            self.set_in_type(page, read, png, trial, dpi)
            verdict = self.judge(page, read, png, trial, dpi, again)
        except layout.LayoutError as e:
            log.warning("page %s: not set again from %s: %s", page.id, READER, e)
            return first, (*why, str(e))
        else:
            if not verdict.passed:
                return first, (*why, *verdict.reasons)
            os.replace(trial, out)
            return verdict, ()
        finally:
            files.remove(trial)

    def stage_export(self, book_id: int, pages: tuple[int, ...] | None = None) -> None:
        export.write_all(book_id, lambda d, t: self._progress(book_id, done=d, total=t))


PICTURES = (
    2  # how a page with no text is made (rebuild_picture); 2: marks lifted off the paper, covers trimmed to the book
)


def made(page: Page) -> bool:
    """Whether the page's rebuilt PDF is the one the rebuild would make now: a text page set and passed by the gate; any other page made the
    current way (PICTURES). Either as the kind it is now: a page whose kind a person changed is made again. Editing its text removes the PDF."""
    if not os.path.isfile(files.rebuilt_pdf(page.book_id, page.id)):
        return False
    if not typeset(page):
        try:
            with open(files.rebuilt_pdf(page.book_id, page.id) + ".json", encoding="utf-8") as f:
                how = cast("dict[str, Any]", json.load(f))
        except (OSError, ValueError):
            return False  # made before the way was written down
        return how.get("way") == PICTURES and how.get("kind") == page.kind
    verdict = cast("dict[str, Any]", (page.ocr or {}).get("gate") or {})
    return bool(verdict.get("passed")) and verdict.get("kind", "text") == page.kind and "way" not in verdict


def typeset(page: Page) -> bool:
    """Whether the page is set in type: a text page with lines read. Any other is its pictures, its pattern or a blank (rebuild_picture)."""
    return page.kind == "text" and bool((page.ocr or {}).get("lines")) and bool((page.text or "").strip())


def resume_from(stage: str) -> tuple[str, ...]:
    """The stages left to do for a book a stop left in `stage`. The rebuild is never begun by this: only finished."""
    if stage == "rebuild":
        return ("rebuild", "export")
    return STAGES[STAGES.index(stage) :] if stage in STAGES else ("detect", "read")


def _catch(work: Callable[[Any], None], item: Any) -> str | None:
    try:
        work(item)
        return None
    except (StageError, sources.SourceError) as e:
        return str(e)
    except Exception as e:
        log.exception("stage item failed")
        return f"{type(e).__name__}: {e}"


def keep_line(line: dict[str, Any], bar: float = 55.0) -> bool:
    """Is an OCR line text, or noise? Tesseract reads the hatching of an engraving, a printed border or a stain as lines of short
    low-confidence "words" (`, iy VevrytnNiy Wu`, `nn CARO OLE EST`). A line is kept when its mean word confidence reaches `bar`, or when
    most of its words are confident (a real line with one smudged word); and it needs two letters or digits, so a lone `q` or `€` goes."""
    text = str(line.get("text", ""))
    if sum(ch.isalnum() for ch in text) < 2:
        return False
    confs = [float(w["conf"]) for w in line.get("words", [])] or [float(line.get("conf", 0))]
    return sum(confs) / len(confs) >= bar or sum(c >= 75 for c in confs) >= 0.6 * len(confs)


def kept_lines(ocr: dict[str, Any], sure_words: int, kind: str = "text") -> list[int]:
    """Which of the OCR's lines are the page's text (their indices): its lines minus the noise (`keep_line`). A page with almost no
    confident words has none; on a cover or a picture page, where most of what Tesseract sees is not type, the bar is higher."""
    if sure_words < 3:
        return []
    bar = 75.0 if kind in ("cover", "picture") else 55.0
    return [i for i, ln in enumerate(ocr.get("lines", [])) if keep_line(ln, bar)]


def clean_text(ocr: dict[str, Any], sure_words: int, kind: str = "text") -> str:
    """The page's text from the OCR: its kept lines (`kept_lines`), one a line."""
    lines = ocr.get("lines", [])
    return "\n".join(str(lines[i]["text"]) for i in kept_lines(ocr, sure_words, kind))


def scan_dpi(page: Page) -> int:
    with store.session() as s:
        scan = s.get(Scan, page.scan_id)
    return scan.dpi if scan and scan.dpi else 300


def renumber(book_id: int) -> None:
    """Pages numbered 1..n in the order of their scans, then left before right."""
    order = {"left": 0, "single": 1, "right": 2}
    with store.session() as s:
        rows = list(
            s.execute(
                select(Page, Scan.position).join(Scan, Page.scan_id == Scan.id).where(Page.book_id == book_id)
            ).all()
        )
        rows.sort(key=lambda r: (r[1], order.get(r[0].side, 1), r[0].id))
        for i, (p, _) in enumerate(rows, 1):
            p.position = i


def render(page: Page) -> None:
    """Draw the page from its scan (full size, preview, thumbnail) and mark it drawn."""
    with store.session() as s:
        scan = s.get(Scan, page.scan_id)
        if scan is None:
            raise StageError(f"page {page.id} has no scan")
        src = os.path.join(files.book_dir(page.book_id), scan.file)
    img = geometry.apply(read_image(src), page.angle, (page.crop_x, page.crop_y, page.crop_w, page.crop_h))
    cv2.imwrite(files.page_png(page.book_id, page.id), img)
    write_jpeg(files.preview(page.book_id, "page", page.id), img, files.PREVIEW)
    write_jpeg(files.preview(page.book_id, "thumb", page.id), img, files.THUMB)
    with store.session() as s:
        s.execute(update(Page).where(Page.id == page.id).values(rendered=True))
