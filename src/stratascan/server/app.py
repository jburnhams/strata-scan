"""The application server: `./strata-scan serve` starts the FastAPI backend and serves the built React app.

    ./strata-scan serve [--host 127.0.0.1] [--port 8368]

At start it migrates the app's schema (the only process that does) and starts the book runner (pipeline.Runner), which picks up any book a
stop left mid-stage. API (JSON unless it is a picture or a file):

    GET    /api/health, GET|PUT /api/settings                       (strata_python.web)
    GET    /api/system                                               versions, data folder, disk, strata-models and its ocr role
    GET    /api/books                                                every book with its page counts and progress
    POST   /api/books {source, title?, author?, lang?}               a PDF or a folder of pictures on this machine; imports and reads it
    POST   /api/books/upload (multipart: file, title?, author?)      a PDF from the browser
    GET    /api/books/{id}   PATCH {title?, author?, lang?}   DELETE
    POST   /api/books/{id}/run {stages, pages?}                      run stages again (detect, read, export; import starts over)
    GET    /api/books/{id}/pages                                     the pages in reading order, without their OCR
    GET    /api/books/{id}/figures                                   every picture in the book
    GET    /api/books/{id}/files/{name}                              book.md, book.txt, book.pdf, book.zip
    GET    /api/pages/{id}                                           a page with its scan, OCR lines and pictures
    PATCH  /api/pages/{id} {angle?, crop?, kind?, label?, text?}     a new turn or cut is hand work: the page is drawn and read again
    PUT    /api/scans/{id}/pages {pages: [{side, angle, crop}]}      the scan's pages set by hand (one page, or a spread's two)
    PUT    /api/pages/{id}/figures {figures: [{x, y, w, h, caption?}]}
    GET    /api/scans/{id}/image?angle=     /api/pages/{id}/image?size=thumb|preview|full     /api/figures/{id}/image

Every other path serves the web app, so a reload or a shared link opens that screen."""

import os
import shutil
import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any

import cv2
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from strata_python import web

from stratascan import __version__, export, files, geometry, pipeline, settings, sources, store, system
from stratascan.db.models import Book, Figure, Page, Scan

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
LANDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing.html")
KINDS = ("text", "picture", "blank", "cover", "skip")


class BookIn(BaseModel):
    source: str
    title: str | None = None
    author: str | None = None
    lang: str = "eng"


class BookPatch(BaseModel):
    title: str | None = None
    author: str | None = None
    lang: str | None = None


class RunIn(BaseModel):
    stages: list[str]
    pages: list[int] | None = None


class Crop(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class PagePatch(BaseModel):
    angle: float | None = Field(default=None, ge=-180, le=180)
    crop: Crop | None = None
    kind: str | None = None
    label: str | None = None
    text: str | None = None


class PageShape(BaseModel):
    side: str = "single"
    angle: float = Field(default=0.0, ge=-180, le=180)
    crop: Crop


class ScanPagesIn(BaseModel):
    pages: list[PageShape] = Field(min_length=1, max_length=2)


class FigureIn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    caption: str | None = None


class FiguresIn(BaseModel):
    figures: list[FigureIn]


def book_json(b: Book, counts: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "id": b.id,
        "title": b.title,
        "author": b.author,
        "source": b.source,
        "lang": b.lang,
        "stage": b.stage,
        "done": b.done,
        "total": b.total,
        "error": b.error,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        **(counts or {}),
    }


def page_json(p: Page, figures: int = 0) -> dict[str, Any]:
    return {
        "id": p.id,
        "book_id": p.book_id,
        "scan_id": p.scan_id,
        "position": p.position,
        "side": p.side,
        "angle": p.angle,
        "crop": {"x": p.crop_x, "y": p.crop_y, "w": p.crop_w, "h": p.crop_h},
        "confidence": p.confidence,
        "hand": p.hand,
        "kind": p.kind,
        "label": p.label,
        "read": p.ocr is not None,
        "ocr_conf": p.ocr_conf,
        "words": len((p.text or "").split()),
        "text_edited": p.text_edited,
        "figures": figures,
        "error": p.error,
    }


def figure_json(f: Figure, p: Page | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": f.id,
        "page_id": f.page_id,
        "x": f.x,
        "y": f.y,
        "w": f.w,
        "h": f.h,
        "caption": f.caption,
        "hand": f.hand,
    }
    if p is not None:
        out |= {"page_position": p.position, "page_label": p.label}
    return out


def counts(book_id: int) -> dict[str, int]:
    with store.session() as s:
        pages = s.scalar(select(func.count()).select_from(Page).where(Page.book_id == book_id)) or 0
        read = (
            s.scalar(select(func.count()).select_from(Page).where(Page.book_id == book_id, Page.ocr.is_not(None))) or 0
        )
        scans = s.scalar(select(func.count()).select_from(Scan).where(Scan.book_id == book_id)) or 0
        figs = (
            s.scalar(
                select(func.count())
                .select_from(Figure)
                .join(Page, Figure.page_id == Page.id)
                .where(Page.book_id == book_id)
            )
            or 0
        )
        check = (
            s.scalar(
                select(func.count())
                .select_from(Page)
                .where(Page.book_id == book_id, Page.confidence < 0.6, Page.hand.is_(False))
            )
            or 0
        )
    return {"scans": scans, "pages": pages, "read": read, "figures": figs, "to_check": check}


def get_or_404(model: Any, item_id: int, what: str) -> Any:
    with store.session() as s:
        row = s.get(model, item_id)
    if row is None:
        raise HTTPException(404, f"there is no {what} {item_id}")
    return row


def busy(book: Book) -> None:
    if book.stage != "idle":
        raise HTTPException(409, f"“{book.title}” is busy ({book.stage}); wait for it to finish")


def jpeg(img: geometry.Image) -> Response:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(500, "could not encode the picture")
    return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


def create_app(runner: pipeline.Runner | None = None, migrate: bool = True) -> FastAPI:
    run = runner or pipeline.Runner()
    app = web.base_app("strata-scan", __version__, settings.SETTINGS)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        if migrate:
            store.migrate()
        run.start()
        run.resume()
        yield
        run.stop()

    app.router.lifespan_context = lifespan

    def new_book(source: str, title: str | None, author: str | None, lang: str) -> dict[str, Any]:
        try:
            kind, _ = sources.describe(source)
        except sources.SourceError as e:
            raise HTTPException(400, str(e)) from e
        name = (
            (title or "").strip()
            or (sources.pdf_title(source) if kind == "pdf" else None)
            or os.path.splitext(os.path.basename(source.rstrip("/\\")))[0]
        )
        with store.session() as s:
            b = Book(title=name[:300], source=source, author=(author or "").strip() or None, lang=lang or "eng")
            s.add(b)
            s.flush()
            book_id = b.id
        run.submit(book_id, pipeline.STAGES)
        return book_json(get_or_404(Book, book_id, "book"), counts(book_id))

    @app.get("/api/system")
    def get_system() -> dict[str, Any]:
        return system.status()

    @app.get("/api/books")
    def get_books() -> list[dict[str, Any]]:
        with store.session() as s:
            books = list(s.scalars(select(Book).order_by(Book.updated_at.desc(), Book.id.desc())))
        return [book_json(b, counts(b.id)) for b in books]

    @app.post("/api/books", status_code=201)
    def post_book(b: BookIn) -> dict[str, Any]:
        return new_book(b.source, b.title, b.author, b.lang)

    @app.post("/api/books/upload", status_code=201)
    def upload_book(
        file: Annotated[UploadFile, File()],
        title: Annotated[str | None, Form()] = None,
        author: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        name = os.path.basename(file.filename or "book.pdf")
        if not name.lower().endswith(".pdf"):
            raise HTTPException(400, f"{name} is not a PDF")
        dest = os.path.join(files.uploads(), f"{uuid.uuid4().hex[:8]}-{name}")
        with open(dest, "wb") as out:
            shutil.copyfileobj(file.file, out)
        return new_book(dest, title, author, "eng")

    @app.get("/api/books/{book_id}")
    def get_book(book_id: int) -> dict[str, Any]:
        b = get_or_404(Book, book_id, "book")
        return book_json(b, counts(book_id)) | {"files": export.made(book_id)}

    @app.patch("/api/books/{book_id}")
    def patch_book(book_id: int, ch: BookPatch) -> dict[str, Any]:
        with store.session() as s:
            b = s.get(Book, book_id)
            if b is None:
                raise HTTPException(404, f"there is no book {book_id}")
            if ch.title is not None:
                if not ch.title.strip():
                    raise HTTPException(422, "a book needs a title")
                b.title = ch.title.strip()
            if ch.author is not None:
                b.author = ch.author.strip() or None
            if ch.lang is not None:
                b.lang = ch.lang.strip() or "eng"
        return get_book(book_id)

    @app.delete("/api/books/{book_id}")
    def delete_book(book_id: int) -> dict[str, Any]:
        b = get_or_404(Book, book_id, "book")
        busy(b)
        with store.session() as s:
            row = s.get(Book, book_id)
            if row is not None:
                s.delete(row)
        files.remove_book(book_id)
        return {"removed": book_id}

    @app.post("/api/books/{book_id}/run", status_code=202)
    def run_book(book_id: int, r: RunIn) -> dict[str, Any]:
        b = get_or_404(Book, book_id, "book")
        busy(b)
        try:
            run.submit(book_id, r.stages, r.pages)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return get_book(book_id)

    @app.get("/api/books/{book_id}/pages")
    def get_pages(book_id: int) -> list[dict[str, Any]]:
        get_or_404(Book, book_id, "book")
        with store.session() as s:
            n = dict(
                s.execute(
                    select(Figure.page_id, func.count())
                    .join(Page, Figure.page_id == Page.id)
                    .where(Page.book_id == book_id)
                    .group_by(Figure.page_id)
                ).all()
            )
            pages = list(s.scalars(select(Page).where(Page.book_id == book_id).order_by(Page.position)))
        return [page_json(p, n.get(p.id, 0)) for p in pages]

    @app.get("/api/books/{book_id}/figures")
    def get_book_figures(book_id: int) -> list[dict[str, Any]]:
        get_or_404(Book, book_id, "book")
        with store.session() as s:
            rows = s.execute(
                select(Figure, Page)
                .join(Page, Figure.page_id == Page.id)
                .where(Page.book_id == book_id)
                .order_by(Page.position, Figure.y)
            ).all()
        return [figure_json(f, p) for f, p in rows]

    @app.get("/api/books/{book_id}/files/{name}")
    def get_file(book_id: int, name: str) -> FileResponse:
        b = get_or_404(Book, book_id, "book")
        if name not in export.NAMES:
            raise HTTPException(404, f"there is no file {name} (files: {', '.join(export.NAMES)})")
        p = os.path.join(files.book_dir(book_id), "export", name)
        if not os.path.isfile(p):
            raise HTTPException(404, f"{name} has not been made yet: make the files first")
        stem = "".join(c if c.isalnum() or c in " -_" else "" for c in b.title)[:80].strip() or "book"
        return FileResponse(p, filename=f"{stem}{os.path.splitext(name)[1]}")

    @app.get("/api/pages/{page_id}")
    def get_page(page_id: int) -> dict[str, Any]:
        with store.session() as s:
            p = s.get(Page, page_id)
            if p is None:
                raise HTTPException(404, f"there is no page {page_id}")
            scan = s.get(Scan, p.scan_id)
            figs = list(s.scalars(select(Figure).where(Figure.page_id == page_id).order_by(Figure.y)))
            siblings = list(s.scalars(select(Page).where(Page.scan_id == p.scan_id).order_by(Page.position)))
            prev_id = s.scalar(
                select(Page.id)
                .where(Page.book_id == p.book_id, Page.position < p.position)
                .order_by(Page.position.desc())
                .limit(1)
            )
            next_id = s.scalar(
                select(Page.id)
                .where(Page.book_id == p.book_id, Page.position > p.position)
                .order_by(Page.position)
                .limit(1)
            )
        lines = [{"text": ln["text"], "box": ln["box"], "conf": ln["conf"]} for ln in (p.ocr or {}).get("lines", [])]
        size = (p.ocr or {}).get("width"), (p.ocr or {}).get("height")
        return page_json(p, len(figs)) | {
            "scan": {
                "id": scan.id,
                "position": scan.position,
                "width": scan.width,
                "height": scan.height,
                "dpi": scan.dpi,
            }
            if scan
            else None,
            "size": {"w": size[0] or p.crop_w, "h": size[1] or p.crop_h},
            "text": p.text,
            "lines": lines,
            "ocr_model": p.ocr_model,
            "figures_list": [figure_json(f) for f in figs],
            "siblings": [
                {
                    "id": x.id,
                    "side": x.side,
                    "angle": x.angle,
                    "crop": {"x": x.crop_x, "y": x.crop_y, "w": x.crop_w, "h": x.crop_h},
                }
                for x in siblings
            ],
            "prev_id": prev_id,
            "next_id": next_id,
        }

    @app.patch("/api/pages/{page_id}")
    def patch_page(page_id: int, ch: PagePatch) -> dict[str, Any]:
        reread = False
        with store.session() as s:
            p = s.get(Page, page_id)
            if p is None:
                raise HTTPException(404, f"there is no page {page_id}")
            book = s.get(Book, p.book_id)
            if ch.kind is not None:
                if ch.kind not in KINDS:
                    raise HTTPException(422, f"a page is one of {', '.join(KINDS)}, not {ch.kind!r}")
                p.kind = ch.kind
            if ch.label is not None:
                p.label = ch.label.strip() or None
            if ch.text is not None:
                p.text, p.text_edited = ch.text, True
            if ch.angle is not None or ch.crop is not None:
                if book is not None:
                    busy(book)
                scan = s.get(Scan, p.scan_id)
                angle = p.angle if ch.angle is None else ch.angle
                if ch.crop is not None:
                    c = (ch.crop.x, ch.crop.y, ch.crop.w, ch.crop.h)
                else:  # a new angle alone keeps the cut's centre and size in the newly turned picture
                    c = (p.crop_x, p.crop_y, p.crop_w, p.crop_h)
                if scan is not None:
                    rw, rh = geometry.rotated_size(scan.width, scan.height, angle)
                    c = geometry.clamp(c, rw, rh)
                p.angle, (p.crop_x, p.crop_y, p.crop_w, p.crop_h), p.hand, p.rendered, p.confidence = (
                    angle,
                    c,
                    True,
                    False,
                    1.0,
                )
                reread = True
            book_id = p.book_id
        if reread:
            run.submit(book_id, ("read",), [page_id])
        return get_page(page_id)

    @app.put("/api/scans/{scan_id}/pages")
    def put_scan_pages(scan_id: int, body: ScanPagesIn) -> list[dict[str, Any]]:
        scan = get_or_404(Scan, scan_id, "scan")
        busy(get_or_404(Book, scan.book_id, "book"))
        if len(body.pages) == 2 and sorted(x.side for x in body.pages) != ["left", "right"]:
            raise HTTPException(422, "a spread's two pages are its left and right")
        with store.session() as s:
            old = list(s.scalars(select(Page).where(Page.scan_id == scan_id)))
            keep_text = {o.side: (o.text, o.label, o.kind) for o in old if o.text_edited}
            for o in old:
                files.remove(
                    files.page_png(o.book_id, o.id),
                    files.preview(o.book_id, "page", o.id),
                    files.preview(o.book_id, "thumb", o.id),
                    files.ocr_pdf(o.book_id, o.id),
                )
                s.delete(o)
            s.flush()
            made: list[int] = []
            for i, x in enumerate(body.pages):
                rw, rh = geometry.rotated_size(scan.width, scan.height, x.angle)
                c = geometry.clamp((x.crop.x, x.crop.y, x.crop.w, x.crop.h), rw, rh)
                p = Page(
                    book_id=scan.book_id,
                    scan_id=scan_id,
                    position=scan.position * 10 + i,
                    side=x.side if len(body.pages) == 2 else "single",
                    angle=x.angle,
                    crop_x=c[0],
                    crop_y=c[1],
                    crop_w=c[2],
                    crop_h=c[3],
                    confidence=1.0,
                    hand=True,
                )
                if p.side in keep_text:
                    p.text, p.label, p.kind = keep_text[p.side]
                    p.text_edited = True
                s.add(p)
                s.flush()
                made.append(p.id)
        pipeline.renumber(scan.book_id)
        run.submit(scan.book_id, ("read",), made)
        with store.session() as s:
            return [page_json(p) for p in s.scalars(select(Page).where(Page.id.in_(made)).order_by(Page.position))]

    @app.put("/api/pages/{page_id}/figures")
    def put_figures(page_id: int, body: FiguresIn) -> list[dict[str, Any]]:
        p: Page = get_or_404(Page, page_id, "page")
        png = files.page_png(p.book_id, p.id)
        img = pipeline.read_image(png) if os.path.isfile(png) else None
        with store.session() as s:
            for f in s.scalars(select(Figure).where(Figure.page_id == page_id)):
                files.remove(files.figure_png(p.book_id, f.id))
                s.delete(f)
            s.flush()
            rows: list[Figure] = []
            for f in body.figures:
                x, y, w, h = f.x, f.y, f.w, f.h
                if img is not None:
                    x, y, w, h = geometry.clamp((x, y, w, h), img.shape[1], img.shape[0])
                rows.append(
                    Figure(page_id=page_id, x=x, y=y, w=w, h=h, caption=(f.caption or "").strip() or None, hand=True)
                )
            s.add_all(rows)
            s.flush()
            out = [figure_json(f) for f in rows]
        if img is not None:
            for f in out:
                cv2.imwrite(
                    files.figure_png(p.book_id, f["id"]), img[f["y"] : f["y"] + f["h"], f["x"] : f["x"] + f["w"]]
                )
        return out

    @app.get("/api/scans/{scan_id}/image")
    def scan_image(scan_id: int, angle: float = Query(0.0, ge=-180, le=180)) -> Response:
        """The scan's preview turned by `angle`: the picture the crop editor draws on. Its size is the turned full scan's times
        `scale` (in the X-Scale header), so the editor converts its rectangle back to full-size pixels."""
        scan: Scan = get_or_404(Scan, scan_id, "scan")
        prev = files.preview(scan.book_id, "scan", scan.id)
        if not os.path.isfile(prev):
            raise HTTPException(404, "the scan has no preview yet: wait for the import to finish")
        img = geometry.rotate(pipeline.read_image(prev), angle)
        r = jpeg(img)
        r.headers["X-Scale"] = f"{img.shape[1] / geometry.rotated_size(scan.width, scan.height, angle)[0]:.6f}"
        return r

    @app.get("/api/pages/{page_id}/image")
    def page_image(page_id: int, size: str = Query("preview", pattern="^(thumb|preview|full)$")) -> FileResponse:
        p: Page = get_or_404(Page, page_id, "page")
        f = (
            files.page_png(p.book_id, p.id)
            if size == "full"
            else files.preview(p.book_id, size if size == "thumb" else "page", p.id)
        )
        if not os.path.isfile(f):
            raise HTTPException(404, "the page has not been drawn yet")
        return FileResponse(f, headers={"Cache-Control": "no-cache"})

    @app.get("/api/figures/{figure_id}/image")
    def figure_image(figure_id: int) -> FileResponse:
        f: Figure = get_or_404(Figure, figure_id, "picture")
        p: Page = get_or_404(Page, f.page_id, "page")
        path = files.figure_png(p.book_id, f.id)
        if not os.path.isfile(path):
            raise HTTPException(404, "the picture has not been cut out yet")
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    web.add_web(app, STATIC, LANDING)
    return app


def main(argv: Sequence[str] | None = None) -> None:
    web.serve(create_app(), argv, default_port=8368, banner=f"data folder: {settings.data_dir()}")
