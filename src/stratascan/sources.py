"""Bringing a book in: a PDF (each page drawn as a picture) or a folder of pictures (copied), as numbered scans in the book's folder.

A PDF page is drawn at the resolution of the scan inside it, not at a fixed dpi: the Internet Archive books this was built on are 360 and
500 dpi, and drawing them at 300 would throw a third of the detail away before OCR sees it, while 600 would double the files for nothing.
The largest picture on the page decides (IA's PDFs layer a low-resolution background under a full-resolution foreground); a page with no
picture (a born-digital PDF) is drawn at 300 dpi. `max_dpi` caps it. pypdfium2 (PDFium, BSD/Apache) draws them: it reads the JPEG 2000 and
JBIG2 layers IA uses, and is a wheel on every platform."""

import os
import re
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pypdfium2 as pdfium  # pyright: ignore[reportMissingTypeStubs]
import pypdfium2.raw as pdfium_c  # pyright: ignore[reportMissingTypeStubs]
from PIL import Image

from stratascan import files

PICTURES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
KEEP = (
    ".png",
    ".jpg",
    ".jpeg",
)  # copied as they are; the rest become PNG (browsers and Tesseract read these three best)


class SourceError(ValueError):
    """The source cannot be imported (missing, not a PDF or pictures, empty, unreadable): said in words for the person."""


@dataclass(frozen=True)
class ScanFile:
    position: int
    file: str  # relative to the book's folder
    width: int
    height: int
    dpi: int | None


def _natural(name: str) -> list[object]:
    """Sort key that puts page 2 before page 10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def pictures_in(folder: str) -> list[str]:
    return sorted(
        (f for f in os.listdir(folder) if f.lower().endswith(PICTURES) and not f.startswith(".")), key=_natural
    )


def describe(source: str) -> tuple[str, int]:
    """("pdf" | "pictures", how many scans) for a source, or SourceError saying why it cannot be imported."""
    if not os.path.isabs(source):
        raise SourceError(f"give the full path of a PDF or a folder of pictures, not {source!r}")
    if os.path.isdir(source):
        n = len(pictures_in(source))
        if n == 0:
            raise SourceError(f"{source} has no pictures in it ({', '.join(PICTURES)})")
        return "pictures", n
    if not os.path.isfile(source):
        raise SourceError(f"there is nothing at {source}")
    if source.lower().endswith(".pdf"):
        try:
            doc = pdfium.PdfDocument(source)
        except pdfium.PdfiumError as e:
            raise SourceError(f"{os.path.basename(source)} is not a PDF that can be read: {e}") from e
        n = len(doc)
        doc.close()
        if n == 0:
            raise SourceError(f"{os.path.basename(source)} has no pages")
        return "pdf", n
    if source.lower().endswith(PICTURES):
        return "pictures", 1
    raise SourceError(f"{os.path.basename(source)} is not a PDF or a picture")


def pdf_title(source: str) -> str | None:
    """The PDF's own title, if it has one (IA's do: "Punch and Judy, with illustrations by George Cruikshank, ...")."""
    try:
        doc = pdfium.PdfDocument(source)
    except pdfium.PdfiumError:
        return None
    try:
        t = str(doc.get_metadata_dict().get("Title") or "").strip()
        return t or None
    finally:
        doc.close()


def page_dpi(page: pdfium.PdfPage, max_dpi: int) -> int:
    width_pt = page.get_width()
    widest = 0
    for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,)):  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(obj, pdfium.PdfImage):
            widest = max(widest, int(obj.get_px_size()[0]))
    dpi = round(widest / width_pt * 72) if widest and width_pt > 0 else 300
    return max(72, min(dpi, max_dpi))


def render_page(page: pdfium.PdfPage, dpi: int) -> Image.Image:
    bitmap = page.render(scale=dpi / 72)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportArgumentType]  (its stub says int; it takes a float)
    pil = bitmap.to_pil()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(pil, Image.Image):
        raise SourceError("PDFium drew something that is not a picture")
    return pil.convert("RGB")


def _pdf(source: str, book_id: int, max_dpi: int) -> Iterator[ScanFile]:
    doc = pdfium.PdfDocument(source)
    try:
        for i in range(len(doc)):
            page = doc[i]
            dpi = page_dpi(page, max_dpi)
            img = render_page(page, dpi)
            name = files.scan_name(i + 1)
            img.save(files.path(book_id, name), dpi=(dpi, dpi))
            page.close()
            yield ScanFile(i + 1, name, img.width, img.height, dpi)
    finally:
        doc.close()


def _pictures(paths: list[str], book_id: int) -> Iterator[ScanFile]:
    for i, src in enumerate(paths, 1):
        ext = os.path.splitext(src)[1].lower()
        try:
            with Image.open(src) as im:
                info_dpi = im.info.get("dpi")
                dpi = round(float(info_dpi[0])) if isinstance(info_dpi, tuple) and info_dpi else None  # pyright: ignore[reportUnknownArgumentType]
                w, h = im.size
                if ext in KEEP:
                    name = files.scan_name(i, ".jpg" if ext == ".jpeg" else ext)
                    shutil.copyfile(src, files.path(book_id, name))
                else:
                    name = files.scan_name(i)
                    im.convert("RGB").save(files.path(book_id, name))
        except OSError as e:
            raise SourceError(f"{os.path.basename(src)} is not a picture that can be read: {e}") from e
        yield ScanFile(i, name, w, h, dpi or None)


def import_scans(
    source: str, book_id: int, max_dpi: int, progress: Callable[[int, int], None] | None = None
) -> list[ScanFile]:
    """Every scan of `source` written into the book's folder, in order; `progress(done, total)` after each."""
    kind, total = describe(source)
    it = (
        _pdf(source, book_id, max_dpi)
        if kind == "pdf"
        else _pictures(
            [os.path.join(source, f) for f in pictures_in(source)] if os.path.isdir(source) else [source], book_id
        )
    )
    out: list[ScanFile] = []
    for s in it:
        out.append(s)
        if progress:
            progress(len(out), total)
    return out
