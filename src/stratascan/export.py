"""A book's files, written into its export folder: what the work is for.

    book.md    the text read through, page after page, with the pictures where they stand on the page: paragraphs joined (a printed line
               break is not a paragraph), words split at a line end with a hyphen joined again, running heads left out
    book.txt   each page's text as it is printed, line for line, under a page marker: for checking and for searching
    book.pdf   every page as drawn, with its text under it (the ocr role's PDF pages joined), so it can be searched and copied
    figures/   every picture as a PNG, named by page (p011-1.png)
    book.zip   all of the above

Pages marked `skip` are left out of every file; `blank` pages are left out of the text but kept in the PDF, so the PDF still turns like
the book. A page with no PDF from the OCR (never read) goes into book.pdf as its picture alone."""

import os
import re
import shutil
import statistics
import zipfile
from collections.abc import Callable
from typing import Any, cast

from PIL import Image
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select

from stratascan import files, store
from stratascan.db.models import Book, Figure, Page, Scan

JPEG_QUALITY = 75
PDF_SIDE = (
    2400  # book.pdf's pages: about 300 dpi for a pocket book, 250-400 kB a page; the full scans stay in the data folder
)
NAMES = ("book.md", "book.txt", "book.pdf", "book.zip")
NUMBER = re.compile(r"^\W*(\d{1,4})\W*$|^\W*(\d{1,4})\b|\b(\d{1,4})\W*$")


def smaller(im: Image.Image | None) -> Image.Image:
    """A page picture for book.pdf: RGB, its long side at most PDF_SIDE (the PDF page keeps its size; only the pixels behind it shrink)."""
    if im is None:
        return Image.new("RGB", (1, 1), "white")
    im = im.convert("RGB")
    if max(im.size) > PDF_SIDE:
        im.thumbnail((PDF_SIDE, PDF_SIDE), Image.Resampling.LANCZOS)
    return im


def page_name(p: Page) -> str:
    return p.label or str(p.position)


def figure_file(p: Page, k: int) -> str:
    return f"figures/p{p.position:03d}-{k}.png"


def page_number(line: str) -> str | None:
    """The printed number in a running head or a foot line ("PUPPET-PLAYS IN ENGLAND. 27" -> "27"), if it has one."""
    m = NUMBER.search(line.strip())
    return next((g for g in m.groups() if g), None) if m else None


def is_running_head(line: str, n_lines: int) -> bool:
    """A page's first line that is a running head ("PUPPET-PLAYS IN ENGLAND. 27", "INTRODUCTION. 5"): short and mostly capitals."""
    letters = [c for c in line if c.isalpha()]
    if n_lines < 4 or not letters or len(line.split()) > 8:
        return False
    return sum(c.isupper() for c in letters) / len(letters) > 0.7


def join_lines(lines: list[str]) -> str:
    """Lines of one paragraph as one. A hyphen at a line end joins without a space: before a lower-case word it is a word the printer split
    ("repre-" "sentation"), and it goes; before anything else it is a real hyphen ("PUPPET-" "PLAYS"), and it stays."""
    out = ""
    for ln in (x.strip() for x in lines):
        if not ln:
            continue
        out = (out[:-1] if ln[:1].islower() else out) + ln if out.endswith("-") else f"{out} {ln}" if out else ln
    return out


def paragraphs(ocr_lines: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """(top y, paragraph) from OCR lines with boxes: a new paragraph where a line is indented or the line before it stopped short, or where
    Tesseract started a new block."""
    if not ocr_lines:
        return []
    lefts = [int(ln["box"][0]) for ln in ocr_lines]
    rights = [int(ln["box"][0]) + int(ln["box"][2]) for ln in ocr_lines]
    heights = [int(ln["box"][3]) for ln in ocr_lines]
    left, right, em = statistics.median(lefts), statistics.median(rights), max(1.0, statistics.median(heights))
    out: list[tuple[int, str]] = []
    cur: list[str] = []
    top = 0
    prev: dict[str, Any] | None = None
    for ln in ocr_lines:
        x, y = int(ln["box"][0]), int(ln["box"][1])
        new = (
            prev is None
            or ln.get("block") != prev.get("block")
            or x > left + 0.8 * em
            or (int(prev["box"][0]) + int(prev["box"][2])) < right - 3 * em
        )
        if new and cur:
            out.append((top, join_lines(cur)))
            cur = []
        if not cur:
            top = y
        cur.append(str(ln["text"]))
        prev = ln
    if cur:
        out.append((top, join_lines(cur)))
    return out


def page_markdown(p: Page, figs: list[Figure]) -> str:
    items: list[tuple[int, str]] = []
    text_lines = list((p.text or "").splitlines())
    if p.text_edited or not p.ocr:
        # a person's text is kept as they wrote it: blank lines are its paragraphs, and nothing is taken out
        body = [join_lines(chunk.splitlines()) for chunk in re.split(r"\n\s*\n", p.text or "")]
        items = [(-1, b) for b in body if b]
    else:
        kept = set(text_lines)
        lines = [ln for ln in p.ocr.get("lines", []) if ln["text"] in kept]
        if lines and is_running_head(str(lines[0]["text"]), len(lines)):
            lines = lines[1:]
        items = paragraphs(lines)
    for k, f in enumerate(figs, 1):
        items.append((f.y, f"![{f.caption or 'Picture on page ' + page_name(p)}]({figure_file(p, k)})"))
    items.sort(key=lambda it: it[0])
    return f"<!-- page {page_name(p)} -->\n\n" + "\n\n".join(t for _, t in items)


def load(book_id: int) -> tuple[Book, list[Page], dict[int, list[Figure]], dict[int, int]]:
    """The book, its pages in order (not the skipped ones), each page's pictures and the resolution of each scan (id -> dpi)."""
    with store.session() as s:
        book = s.get(Book, book_id)
        if book is None:
            raise KeyError(book_id)
        pages = list(
            s.scalars(select(Page).where(Page.book_id == book_id, Page.kind != "skip").order_by(Page.position))
        )
        figs: dict[int, list[Figure]] = {}
        for f in s.scalars(
            select(Figure).join(Page, Figure.page_id == Page.id).where(Page.book_id == book_id).order_by(Figure.y)
        ):
            figs.setdefault(f.page_id, []).append(f)
        dpi = {sc.id: sc.dpi or 300 for sc in s.scalars(select(Scan).where(Scan.book_id == book_id))}
    return book, pages, figs, dpi


def write_all(book_id: int, progress: Callable[[int, int], None] | None = None) -> dict[str, str]:
    book, pages, figs, dpi = load(book_id)
    total = len(pages) + 3

    def tick(done: int, of: int) -> None:
        if progress:
            progress(done, of)

    out_dir = os.path.dirname(files.export(book_id, "x"))
    shutil.rmtree(os.path.join(out_dir, "figures"), ignore_errors=True)
    os.makedirs(os.path.join(out_dir, "figures"))
    head = f"# {book.title}\n\n" + (f"{book.author}\n\n" if book.author else "")
    md, txt = [head], [f"{book.title}\n"]
    pdf = PdfWriter()
    for i, p in enumerate(pages, 1):
        pf = figs.get(p.id, [])
        for k, f in enumerate(pf, 1):
            src = files.figure_png(book_id, f.id)
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(out_dir, figure_file(p, k)))
        if p.kind != "blank":
            md.append(page_markdown(p, pf))
            txt.append(f"\n--- page {page_name(p)} ---\n{p.text or ''}")
        ocr = files.ocr_pdf(book_id, p.id)
        png = files.page_png(book_id, p.id)
        if os.path.isfile(ocr) and os.path.getsize(ocr) > 0:
            for pg in PdfReader(ocr).pages:
                added = pdf.add_page(pg)
                # Tesseract embeds the page losslessly (3-5 MB a page): a smaller JPEG is a tenth of that
                for im in added.images:
                    picture = cast("Image.Image | None", im.image)  # pyright: ignore[reportUnknownMemberType]  (pypdf types PIL loosely)
                    im.replace(smaller(picture), quality=JPEG_QUALITY)  # pyright: ignore[reportUnknownMemberType]
        elif os.path.isfile(png):
            one = files.path(book_id, "export", ".page.pdf")
            with Image.open(png) as im:
                small = smaller(im)
                # a page never read is the picture alone, at its paper size: the scan's resolution, scaled with the picture
                small.save(
                    one, "PDF", resolution=dpi.get(p.scan_id, 300) * small.width / im.width, quality=JPEG_QUALITY
                )
            for pg in PdfReader(one).pages:
                pdf.add_page(pg)
            os.remove(one)
        tick(i, total)
    paths = {n: files.export(book_id, n) for n in NAMES}
    with open(paths["book.md"], "w", encoding="utf8") as f:
        f.write("\n\n".join(md).rstrip() + "\n")
    tick(len(pages) + 1, total)
    with open(paths["book.txt"], "w", encoding="utf8") as f:
        f.write("\n".join(txt).rstrip() + "\n")
    pdf.add_metadata({"/Title": book.title, **({"/Author": book.author} if book.author else {})})
    with open(paths["book.pdf"], "wb") as f:
        pdf.write(f)
    tick(len(pages) + 2, total)
    with zipfile.ZipFile(paths["book.zip"], "w", zipfile.ZIP_DEFLATED) as z:
        for n in ("book.md", "book.txt", "book.pdf"):
            z.write(paths[n], n)
        for name in sorted(os.listdir(os.path.join(out_dir, "figures"))):
            z.write(os.path.join(out_dir, "figures", name), f"figures/{name}")
    tick(total, total)
    return paths


def made(book_id: int) -> dict[str, float]:
    """The export files that exist, with their modification times (seconds since the epoch)."""
    out: dict[str, float] = {}
    for n in NAMES:
        p = os.path.join(files.book_dir(book_id), "export", n)
        if os.path.isfile(p):
            out[n] = os.path.getmtime(p)
    return out
