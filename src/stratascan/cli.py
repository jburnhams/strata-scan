"""Command line: `doctor` checks the environment, `add` imports and reads a book (the same work the web app starts), `books` lists them,
`run` runs stages again, `export` writes a book's files, `serve` starts the web server. Commands that change books run the stages in this
process and wait; they do not migrate the database (only `serve` does), so run the server once first on a new database."""

import argparse
import json
import sys
import time
from collections.abc import Sequence

from sqlalchemy import select
from strata_python import cli as shared

from stratascan import __version__, export, pipeline, settings, sources, store
from stratascan.db.models import Book


def run_server(host: str, port: int) -> None:
    from stratascan.server import app as server_app

    server_app.main(["--host", host, "--port", str(port)])


def _work(book_id: int, stages: Sequence[str], pages: Sequence[int] | None = None) -> int:
    with store.session() as s:
        if s.get(Book, book_id) is None:
            sys.exit(f"there is no book {book_id} (./strata-scan books lists them)")
    r = pipeline.Runner()
    t0 = time.monotonic()
    r.run(pipeline.Task(book_id, tuple(stages), None if pages is None else tuple(pages)))
    with store.session() as s:
        b = s.get(Book, book_id)
    if b is None:  # removed while it ran
        return 1
    print(f"book {book_id}: {', '.join(stages)} in {time.monotonic() - t0:.0f} s" + (f"; {b.error}" if b.error else ""))
    return 1 if b.error else 0


def cmd_add(args: argparse.Namespace) -> int:
    import os

    source = os.path.abspath(args.source)
    try:
        kind, n = sources.describe(source)
    except sources.SourceError as e:
        sys.exit(str(e))
    title = (
        args.title
        or (sources.pdf_title(source) if kind == "pdf" else None)
        or os.path.splitext(os.path.basename(source.rstrip("/")))[0]
    )
    with store.session() as s:
        b = Book(title=title, source=source, author=args.author, lang=args.lang)
        s.add(b)
        s.flush()
        book_id = b.id
    print(f"book {book_id}: {title} ({n} {'pages' if kind == 'pdf' else 'pictures'})")
    return _work(book_id, pipeline.STAGES if not args.no_read else ("import", "detect"))


def cmd_books(args: argparse.Namespace) -> int:
    from stratascan.server.app import book_json, counts  # the same shape and counts as GET /api/books

    with store.session() as s:
        books = list(s.scalars(select(Book).order_by(Book.id)))
    rows = [book_json(b, counts(b.id)) for b in books]
    if args.json:
        print(json.dumps(rows, indent=1))
        return 0
    pages = {r["id"]: r["pages"] for r in rows}
    for b in books:
        print(f"  #{b.id:<4} {b.title[:60]:60} {pages[b.id]:>4} pages  {b.stage}{'  ' + b.error if b.error else ''}")
    if not books:
        print("  (no books yet: ./strata-scan add /path/to/book.pdf)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    return _work(args.book, args.stages, args.pages)


def cmd_export(args: argparse.Namespace) -> int:
    for name, path in export.write_all(args.book).items():
        print(f"  {name:9} {path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="strata-scan")
    sub = p.add_subparsers(dest="cmd", required=True)
    shared.add_doctor(
        sub,
        "strata-scan",
        __version__,
        (
            "fastapi",
            "uvicorn",
            "pydantic",
            "strata_python",
            "cv2",
            "pypdfium2",
            "pypdf",
            "omarchy_db",
            "strata_models_client",
        ),
    )
    a = sub.add_parser(
        "add", help="import a PDF or a folder of pictures as a book, find its pages, read them and write its files"
    )
    a.add_argument("source")
    a.add_argument("--title")
    a.add_argument("--author")
    a.add_argument("--lang", default="eng", help="Tesseract languages, e.g. eng or eng+fra")
    a.add_argument("--no-read", action="store_true", help="stop after finding the pages (no OCR, no files)")
    a.set_defaults(fn=cmd_add)
    b = sub.add_parser("books", help="list the books")
    b.add_argument("--json", action="store_true")
    b.set_defaults(fn=cmd_books)
    r = sub.add_parser("run", help="run stages of a book again")
    r.add_argument("book", type=int)
    r.add_argument("stages", nargs="+", choices=pipeline.STAGES)
    r.add_argument("--pages", type=int, nargs="+", help="only these page ids")
    r.set_defaults(fn=cmd_run)
    e = sub.add_parser("export", help="write a book's files (book.md, book.txt, book.pdf, book.zip)")
    e.add_argument("book", type=int)
    e.set_defaults(fn=cmd_export)
    shared.add_set(sub, settings.SETTINGS)
    shared.add_serve(sub, run_server, default_port=8368)
    ns = p.parse_args(argv)
    return ns.fn(ns)
