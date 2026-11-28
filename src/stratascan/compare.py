"""A page as scanned against the same page as finished (Jonathan, 2026-11-28: "view both processed and original at the same time ... calc page
quality/matching stats so just bad ones can be viewed"). The web app's compare screen draws the two over or beside each other; this module
gives it the finished page as a picture the same size as the page's preview, so a swipe or an overlay lines up pixel for pixel, a spread of
either as one picture, and, for each page, how well the two agree and whether it is one to look at.

The quality gate (gate.py, owned by the rebuild) already judges a page set in type, on its text lines, before the page is kept; its verdict
is read here, never made again. What this adds is the same measure over the whole page, for every page the finished PDF has: a picture page,
a cover, a blank, which the gate never sees, and the pictures on a text page, which the gate leaves out (its ink is the text lines'). So:

    ink      the finished page's ink against the scan's, over the whole page (gate.ink_of and gate.ink_f1, the gate's own measure, at a
             preview's size and with a looser reach, as a re-set line sits a little off the printed one): below INK the page is to look at
    lost     the scan has ink and the finished page almost none (LOST of it or less): a picture cut short or left out, text not set
    shape    the finished page's width over height differs from the scan's by more than SHAPE: a crop gone wrong, a page set on the wrong
             paper size. Covers are trimmed to the book (marks.book_box), so theirs is not counted
    gate     the gate's reasons, for a text page that failed it

The marks are first guesses (2026-11-28), set before any book was looked at with them: INK at 0.5 because a text page that passes the gate
(0.70 on its lines) scores lower over the whole page, its paper's specks and the gutter counted as the scan's ink. Move them when a book shows
pages wrongly flagged or missed, and say so in the changelog.

Everything here is worked out from the files and kept beside them (previews/finished-<page>.jpg and .json), made again only when the
page's preview or its finished PDF is newer: listing a book's pages the first time renders each finished page once (about a tenth of a
second each), and after that only those set again since."""

import json
import os
from dataclasses import dataclass
from typing import Any, cast

import cv2
import numpy as np
import pypdfium2 as pdfium  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray
from sqlalchemy import select

from stratascan import files, gate, store
from stratascan.db.models import Page, Scan

INK = 0.5
LOST = 0.1
SHAPE = 0.03
SIDE = 1000  # long side the measures are taken at: a line of type is still several pixels tall, and a page takes a few hundredths of a second
VERSION = 1  # bumped when a measure changes, so a kept result is worked out again

Gray = NDArray[np.uint8]


@dataclass(frozen=True)
class Match:
    """How a finished page agrees with its scan."""

    ink: float  # 0-1, gate.ink_f1 over the whole page
    ink_scan: float  # share of the page that is ink, in each
    ink_finished: float
    shape: float  # |aspect - aspect| / the scan's aspect

    def record(self) -> dict[str, Any]:
        return {
            "ink": round(self.ink, 4),
            "ink_scan": round(self.ink_scan, 5),
            "ink_finished": round(self.ink_finished, 5),
            "shape": round(self.shape, 4),
        }


def finished_pdf(p: Page) -> str | None:
    """The page's finished PDF, if it has been made."""
    f = files.rebuilt_pdf(p.book_id, p.id)
    return f if os.path.isfile(f) else None


def render_pdf(pdf: str, width: int) -> Gray:
    """The PDF's first page drawn `width` pixels wide, in grey."""
    doc = pdfium.PdfDocument(pdf)
    try:
        page = cast("Any", doc[0])
        img = np.asarray(
            page.render(scale=width / float(page.get_size()[0]), grayscale=True).to_numpy(), dtype=np.uint8
        )
    finally:
        doc.close()
    return np.asarray(img.reshape(img.shape[:2]), dtype=np.uint8)


def newer(out: str, *sources: str) -> bool:
    """Whether `out` is there and no older than every source."""
    return os.path.isfile(out) and all(os.path.getmtime(out) >= os.path.getmtime(s) for s in sources)


def finished_preview(p: Page) -> str | None:
    """The finished page as a JPEG as wide as the page's preview (previews/finished-<page>.jpg), so the two line up in an overlay; its height
    is the finished page's own, so a page set on the wrong shape shows as one. None when the page has no preview or no finished PDF."""
    pdf = finished_pdf(p)
    prev = files.preview(p.book_id, "page", p.id)
    if pdf is None or not os.path.isfile(prev):
        return None
    out = files.preview(p.book_id, "finished", p.id)
    if not newer(out, pdf, prev):
        scan = cv2.imread(prev, cv2.IMREAD_GRAYSCALE)
        if scan is None:
            return None
        cv2.imwrite(out, render_pdf(pdf, scan.shape[1]), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return out


def measure(scan: Gray, finished: Gray, dpi: float) -> Match:
    """The finished page's agreement with the scan, both in grey. `dpi`: the scan's, at the size it is given."""
    h, w = scan.shape
    shape = abs(finished.shape[1] / finished.shape[0] - w / h) / (w / h)
    want = gate.ink_of(scan, dpi)
    got = np.asarray(cv2.resize(finished, (w, h), interpolation=cv2.INTER_AREA) < 128, dtype=np.bool_)
    everywhere = np.ones((h, w), dtype=np.bool_)
    ink = gate.ink_f1(want, got, max(2, round(dpi / 100)), everywhere)
    return Match(ink=ink, ink_scan=float(want.mean()), ink_finished=float(got.mean()), shape=shape)


def match(p: Page, dpi: int) -> Match | None:
    """The page's measures, kept in previews/finished-<page>.json beside its picture and worked out again when either side changes. None
    when the page has no finished PDF. `dpi`: its scan's."""
    fin = finished_preview(p)
    prev = files.preview(p.book_id, "page", p.id)
    if fin is None:
        return None
    kept = os.path.splitext(fin)[0] + ".json"
    if newer(kept, fin, prev):
        with open(kept, encoding="utf-8") as f:
            r = json.load(f)
        if r.get("version") == VERSION:
            return Match(ink=r["ink"], ink_scan=r["ink_scan"], ink_finished=r["ink_finished"], shape=r["shape"])
    scan = cv2.imread(prev, cv2.IMREAD_GRAYSCALE)
    done = cv2.imread(fin, cv2.IMREAD_GRAYSCALE)
    if scan is None or done is None:
        return None
    s = min(1.0, SIDE / max(scan.shape))
    small = cv2.resize(
        scan, (max(1, round(scan.shape[1] * s)), max(1, round(scan.shape[0] * s))), interpolation=cv2.INTER_AREA
    )
    # the preview's dpi: the scan's, scaled from the page's full width (its crop) to the preview's and then to this size
    full_w = p.crop_w or scan.shape[1]
    m = measure(np.asarray(small, dtype=np.uint8), np.asarray(done, dtype=np.uint8), dpi * small.shape[1] / full_w)
    with open(kept, "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, **m.record()}, f)
    return m


def faults(p: Page, m: Match | None, verdict: dict[str, Any] | None) -> list[str]:
    """Why the page is one to look at, in words; empty when it is not."""
    if m is None:
        return ["not set yet"]
    why: list[str] = []
    if verdict is not None and not verdict.get("passed", True):
        why += [str(r) for r in verdict.get("reasons", [])]
    if m.ink_scan > 0.002 and m.ink_finished <= LOST * m.ink_scan:
        why.append("the finished page has almost none of the scan's ink")
    elif m.ink < INK and p.kind != "cover":
        why.append(f"the ink agrees only {round(100 * m.ink)}%")
    if m.shape > SHAPE and p.kind != "cover":
        why.append(f"the finished page is {round(100 * m.shape)}% a different shape")
    return why


def page_record(p: Page, dpi: int) -> dict[str, Any]:
    """A page's comparison as the API gives it."""
    m = match(p, dpi)
    verdict = cast("dict[str, Any] | None", (p.ocr or {}).get("gate")) if m is not None else None
    why = faults(p, m, verdict)
    return {
        "page_id": p.id,
        "position": p.position,
        "label": p.label,
        "kind": p.kind,
        "side": p.side,
        "scan_id": p.scan_id,
        "finished": m is not None,
        "match": m.record() if m else None,
        "gate": {"passed": bool(verdict["passed"]), "reasons": list(verdict["reasons"])} if verdict else None,
        "look": bool(why),
        "why": why,
    }


def book_records(book_id: int) -> list[dict[str, Any]]:
    """Every page the finished PDF has (all but skipped ones), in reading order, compared."""
    with store.session() as s:
        dpi = {i: d or 300 for i, d in s.execute(select(Scan.id, Scan.dpi).where(Scan.book_id == book_id)).all()}
        pages = list(
            s.scalars(select(Page).where(Page.book_id == book_id, Page.kind != "skip").order_by(Page.position))
        )
    return [page_record(p, dpi.get(p.scan_id, 300)) for p in pages]


def spread(left: str, right: str | None) -> NDArray[np.uint8]:
    """Two pages side by side at the taller one's height, as one picture (colour); one page alone when `right` is None."""
    imgs: list[NDArray[np.uint8]] = []
    for f in (left, right):
        img = cv2.imread(f, cv2.IMREAD_COLOR) if f else None
        if img is not None:
            imgs.append(np.asarray(img, dtype=np.uint8))
    if not imgs:
        raise FileNotFoundError(left)
    h = max(i.shape[0] for i in imgs)
    sized = [
        i if i.shape[0] == h else np.asarray(cv2.resize(i, (round(i.shape[1] * h / i.shape[0]), h)), dtype=np.uint8)
        for i in imgs
    ]
    out = np.zeros((h, sum(i.shape[1] for i in sized), 3), dtype=np.uint8)
    x = 0
    for i in sized:
        out[:, x : x + i.shape[1]] = i
        x += i.shape[1]
    return out
