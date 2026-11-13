"""Where a book's pictures live in the data folder. One folder per book, named by its id, so removing a book is removing a folder:

    books/<book>/scans/0001.png        the scans as imported (a PDF page drawn at its own resolution, or the picture copied)
    books/<book>/pages/<page>.png      a page: its scan turned and cut (geometry.apply), full resolution; OCR reads this
    books/<book>/ocr/<page>.pdf        the page with its text under it, from the ocr role; joined into the book's searchable PDF
    books/<book>/figures/<figure>.png  a picture cut from a page
    books/<book>/previews/...          smaller JPEGs for the web app: scan-<scan>.jpg and page-<page>.jpg (PREVIEW px), thumb-<page>.jpg
    books/<book>/export/               book.md, book.txt, book.pdf, book.zip
    uploads/                           PDFs sent from the browser before they become books

Pages and figures are named by id, not position, so reordering never renames a file and a stale file is never mistaken for another page's."""

import os
import shutil

from stratascan import settings

PREVIEW = (
    1600  # long side of the previews the editor draws on: sharp on a laptop screen, a tenth of a full scan's bytes
)
THUMB = 360


def book_dir(book_id: int) -> str:
    return os.path.join(settings.data_dir(), "books", str(book_id))


def path(book_id: int, *parts: str) -> str:
    """A file in the book's folder, its folder created."""
    p = os.path.join(book_dir(book_id), *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def scan_name(position: int, ext: str = ".png") -> str:
    return f"scans/{position:04d}{ext}"


def page_png(book_id: int, page_id: int) -> str:
    return path(book_id, "pages", f"{page_id}.png")


def ocr_pdf(book_id: int, page_id: int) -> str:
    return path(book_id, "ocr", f"{page_id}.pdf")


def figure_png(book_id: int, figure_id: int) -> str:
    return path(book_id, "figures", f"{figure_id}.png")


def preview(book_id: int, kind: str, item_id: int) -> str:
    """kind: scan, page or thumb."""
    return path(book_id, "previews", f"{kind}-{item_id}.jpg")


def export(book_id: int, name: str) -> str:
    return path(book_id, "export", name)


def uploads() -> str:
    d = os.path.join(settings.data_dir(), "uploads")
    os.makedirs(d, exist_ok=True)
    return d


def remove_book(book_id: int) -> None:
    shutil.rmtree(book_dir(book_id), ignore_errors=True)


def remove(*paths: str) -> None:
    for p in paths:
        if os.path.exists(p):
            os.remove(p)
