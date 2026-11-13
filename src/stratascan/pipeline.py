"""The work on a book, in stages, on one background thread of the server (`Runner`):

    import   the source becomes numbered scans (sources.py) and their previews
    detect   each scan's pages are found (geometry.find_pages), drawn (pages/<id>.png) and numbered in reading order
    read     each page is read by strata-models' `ocr` role (lines, words, a searchable PDF page), its pictures found (figures.py) and cut out,
             and its kind guessed (text, picture, blank, cover)
    export   the book's files are written (export.py)

A stage works on the whole book or on some pages (`pages`: after a person moves a crop, only that page is drawn and read again). Hand work
is kept: detect leaves a scan alone if a person set any of its pages, read keeps a corrected text and hand-drawn pictures. One book stage
runs at a time, so two requests never write the same files; inside a stage, pages are done `settings.workers` at once (OCR waits on the
strata-models service, the pixel work in OpenCV releases the GIL). Progress is the book's `stage`, `done` and `total`, which the web app
polls; a failure is the book's `error` and the failing page's `error`, in words, and the stage carries on with the other pages.

The OCR function is a parameter (`Runner(ocr=...)`) only so the strata-models service can be stood in for: by default it is the client."""

import logging
import os
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Any

import cv2
import numpy as np
import strata_models_client as sm  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import delete, select, update

from stratascan import export, figures, files, geometry, settings, sources, store
from stratascan.db.models import Book, Figure, Page, Scan

log = logging.getLogger("stratascan")
APP = "strata-scan"
STAGES = ("import", "detect", "read", "export")
# (page png, pdf to write, languages, the scan's dpi) -> the ocr role's answer. The dpi matters twice: Tesseract sizes type by it, and the
# PDF page it writes is the picture's pixels at that dpi (without it a 500 dpi page came out as a 1 m tall PDF page).
OcrFn = Callable[[str, str, str, int], dict[str, Any]]


def models_ocr(path: str, pdf: str, lang: str, dpi: int) -> dict[str, Any]:
    try:
        return dict(sm.run("ocr", {"path": path, "pdf": pdf, "lang": lang, "dpi": dpi}, app=APP))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    except sm.Unavailable as e:  # pyright: ignore[reportUnknownMemberType]
        raise StageError(f"strata-models is not running ({e}); start it, then read the pages again") from e
    except sm.JobFailed as e:  # pyright: ignore[reportUnknownMemberType]
        raise StageError(f"strata-models could not read the page: {e}") from e


class StageError(RuntimeError):
    """A failure to show the person, in words."""


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
    def __init__(self, ocr: OcrFn = models_ocr) -> None:
        self.ocr = ocr
        self._q: deque[Task] = deque()
        self._cv = threading.Condition()
        self._busy = False
        self._stop = False
        self._thread: threading.Thread | None = None

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
        bad = [s for s in stages if s not in STAGES]
        if bad:
            raise ValueError(f"no stage {bad[0]!r} (stages: {', '.join(STAGES)})")
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
                self._q.append(Task(book_id, STAGES[STAGES.index(stage) :] if stage in STAGES else ("detect", "read")))
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

    def _each(self, book_id: int, items: list[Any], work: Callable[[Any], None]) -> list[str]:
        """`work` on every item, `settings.workers` at once, counting progress; the failures, in words."""
        errors: list[str] = []
        self._progress(book_id, done=0, total=len(items))
        done = 0
        with ThreadPoolExecutor(max_workers=settings.workers()) as pool:
            for err in pool.map(partial(_catch, work), items):
                done += 1
                if err:
                    errors.append(err)
                self._progress(book_id, done=done)
        return errors

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
        errors = self._each(book_id, todo, lambda p: self.read_page(p, lang))
        if errors:
            self._progress(book_id, error=f"{len(errors)} of {len(todo)} pages could not be read: {errors[0]}")

    def read_page(self, page: Page, lang: str) -> None:
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
        with store.session() as s:
            p = s.get(Page, page.id)
            if p is None:
                return
            first = p.ocr is None
            p.ocr, p.ocr_model, p.error = r, str(r.get("model") or r.get("engine") or "ocr"), None
            p.ocr_conf = round(sum(confs) / len(confs), 1) if confs else None
            img_area = float(img.shape[0] * img.shape[1])
            if first and p.kind == "text":
                area = sum(w * h for _, _, w, h in boxes) / img_area
                p.kind = "picture" if area > 0.3 and sure < 25 else "blank" if not boxes and sure < 3 else "text"
            if not p.text_edited:
                p.text = clean_text(r, sure, p.kind)
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
        for fid, x, y, w, h in cut:
            cv2.imwrite(files.figure_png(page.book_id, fid), img[y : y + h, x : x + w])

    def stage_export(self, book_id: int, pages: tuple[int, ...] | None = None) -> None:
        export.write_all(book_id, lambda d, t: self._progress(book_id, done=d, total=t))


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


def clean_text(ocr: dict[str, Any], sure_words: int, kind: str = "text") -> str:
    """The page's text from the OCR: its lines, minus the noise (`keep_line`). A page with almost no confident words has no text; on a
    cover or a picture page, where most of what Tesseract sees is not type, the bar is higher."""
    if sure_words < 3:
        return ""
    bar = 75.0 if kind in ("cover", "picture") else 55.0
    return "\n".join(str(ln["text"]) for ln in ocr.get("lines", []) if keep_line(ln, bar))


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
