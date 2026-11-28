"""Checks of a rebuilt page's look, beside the gate's words and ink (gate.py): the faults Jonathan found reading the third book's first PDF
(2026-11-28), each made a check so the next book's are found before he reads it. In words, each a reason the page fails:

    weight    a line's words set in weights that differ (STROKE): words set bold mid-page, from a fit that weighed each word alone
    stray     a word set at a size far from its line's (STRAY): "secretly," at two thirds size over the word after it
    overlap   any word drawn over another (OVER of the smaller): the gate's own overlap counts characters over a page and let one word pass
    cut       a picture whose ink runs on past where it was cut (CUT of the page): an engraving's top lost to a layout's guessed box
    missing   a picture the read found that is not drawn: a layout's box in the wrong units, drawn nowhere
    under     a line of the page's text with a picture drawn over it (UNDER of the line): the scan's text under the type, bold and blurred
    size      the page larger than A4, or weighing more than HEAVY: a PDF's pages taken as 72 dpi, pictures stored losslessly
    text      a page read surely (pipeline.READABLE) made as a picture page: the jacket flap's text kept as a picture

Everything is measured in the scan's pixels (top down): the PDF's points scaled by the scan's width over the page's."""

import ctypes
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pypdfium2 as pdfium  # pyright: ignore[reportMissingTypeStubs]
import pypdfium2.raw as pdfium_c  # pyright: ignore[reportMissingTypeStubs]

Box = tuple[float, float, float, float]  # x0, y0, x1, y1

STROKE = 0.2  # share by which a word's stroke may differ from its line's median before the line is uneven
LIGHT = 0.1  # points by which a stroke must differ as well: a heading's hairline strokes differ by hundredths
STRAY = 0.2  # share by which a word's height may differ from its line's median (in a line of one size)
OVER = 0.3  # share of the smaller of two words that lies under the other for them to overlap
CUT = 0.02  # share of the page's side that a picture's ink runs on past its cut
UNDER = 0.1  # share of a line of text under a picture for the line to be covered (the third book's page 11: a third of seven lines, bold)
A4_PT = (595.0 * 1.05, 842.0 * 1.05)  # the page's largest size in points (A4, and a little)
PICTURE = 0.03  # share of the page's side a drawn image is wider and taller than to be a picture (not a rule)
HEAVY = 4_000_000  # bytes a page may weigh: a page with a plate is a few hundred kilobytes as JPEG


@dataclass
class Drawn:
    words: list[
        tuple[Box, float, float]
    ]  # each drawn run of text (a word): its box, its stroke (0: filled only), its type size
    texts: list[str]  # what each says
    pictures: list[Box]
    size: tuple[float, float]  # the page in points
    k: float  # scan pixels a point


def drawn(pdf: str, scan_width: float) -> Drawn:
    """The page's words (text objects) and pictures (image objects), in the scan's pixels."""
    doc = cast("Any", pdfium.PdfDocument(pdf))
    c_api = cast("Any", pdfium_c)
    try:
        page = doc[0]
        wide, high = (float(v) for v in page.get_size())
        k = scan_width / wide if wide > 0 else 1.0

        def box(b: Sequence[float]) -> Box:
            left, bottom, right, top = (float(v) for v in b)
            return (left * k, (high - top) * k, right * k, (high - bottom) * k)

        words: list[tuple[Box, float, float]] = []
        texts: list[str] = []
        tp = page.get_textpage()
        for o in page.get_objects(filter=[c_api.FPDF_PAGEOBJ_TEXT]):
            left, bottom, right, top = (float(v) for v in o.get_bounds())
            texts.append(str(tp.get_text_bounded(left, bottom, right, top)).strip())
            w, fs = ctypes.c_float(0.0), ctypes.c_float(0.0)
            c_api.FPDFPageObj_GetStrokeWidth(o.raw, ctypes.byref(w))
            c_api.FPDFTextObj_GetFontSize(o.raw, ctypes.byref(fs))
            stroked = int(c_api.FPDFTextObj_GetTextRenderMode(o.raw)) in (
                1,
                2,
                5,
                6,
            )  # stroke, fill and stroke, and their clipping kinds
            words.append((box(o.get_bounds()), float(w.value) if stroked else 0.0, float(fs.value)))
        # a picture, not a rule page-build draws as a thin image (more than PICTURE of the page each way)
        pictures = [
            b
            for b in (box(o.get_bounds()) for o in page.get_objects(filter=[c_api.FPDF_PAGEOBJ_IMAGE]))
            if b[2] - b[0] > PICTURE * wide * k and b[3] - b[1] > PICTURE * high * k
        ]
        return Drawn(words, texts, pictures, (wide, high), k)
    finally:
        doc.close()


def lines_of(words: list[tuple[Box, float, float]]) -> list[list[tuple[Box, float, float]]]:
    """The words gathered into lines: those whose middles stand within half a word's height of each other, left to right."""
    rows: list[list[tuple[Box, float, float]]] = []
    for w in sorted(words, key=lambda w: (w[0][1] + w[0][3]) / 2):
        mid, h = (w[0][1] + w[0][3]) / 2, w[0][3] - w[0][1]
        if rows:
            last = rows[-1]
            lm = float(np.median([(b[1] + b[3]) / 2 for b, _, _ in last]))
            if abs(mid - lm) < 0.5 * max(h, 1.0):
                last.append(w)
                continue
        rows.append([w])
    return [sorted(r, key=lambda w: w[0][0]) for r in rows]


def uneven_weight(page: Drawn) -> int:
    """Lines of 4 words or more with a word (of some width: not a lone "a") stroked more than STROKE (and LIGHT points) from the line's
    median: a word set bold, or a run of them, mid-line."""
    n = 0
    for row in lines_of(page.words):
        if len(row) < 4:
            continue
        usual = float(np.median([s for _, s, _ in row]))
        span = max(b[2] for b, _, _ in row) - min(b[0] for b, _, _ in row)
        if any(abs(s - usual) > max(STROKE * usual, LIGHT * page.k) and b[2] - b[0] > 0.04 * span for b, s, _ in row):
            n += 1
    return n


def stray_words(page: Drawn) -> int:
    """Words (of two letters or more: a footnote's mark, a stop or a page number may be set smaller or larger on purpose) set at a type size
    more than STRAY from their line's median, in lines of one size (most of their words within it)."""
    said = {id(w): t for w, t in zip(page.words, page.texts, strict=True)}
    n = 0
    for row in lines_of(page.words):
        if len(row) < 4:
            continue
        usual = float(np.median([size for _, _, size in row]))
        odd = [w for w in row if abs(w[2] / max(usual, 1e-6) - 1) > STRAY]
        if odd and len(odd) <= 0.25 * len(
            row
        ):  # a line of several sizes on purpose (an advert's) is not one stray word
            n += sum(1 for w in odd if sum(c.isalpha() for c in said.get(id(w), "")) >= 2)
    return n


def overlapping_words(page: Drawn) -> int:
    """Pairs of words one over the other by more than OVER of the smaller."""
    boxes = [b for b, _, _ in page.words]
    n = 0
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            w = min(a[2], b[2]) - max(a[0], b[0])
            h = min(a[3], b[3]) - max(a[1], b[1])
            if w <= 0 or h <= 0:
                continue
            small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if w * h > OVER * max(small, 1e-6):
                n += 1
    return n


def cut_short(page: Drawn, png: str, text: Sequence[Box]) -> list[str]:
    """The sides of each picture whose ink runs on past its cut by more than CUT of the page (`layout.picture_box` finds the ink)."""
    from PIL import Image

    from stratascan import layout

    with Image.open(png) as im:
        wide, high = im.size
    lines = [(round(x0), round(y0), round(x1 - x0), round(y1 - y0)) for x0, y0, x1, y1 in text]
    out: list[str] = []
    for x0, y0, x1, y1 in page.pictures:
        if (x1 - x0) * (y1 - y0) > 0.9 * wide * high:
            continue  # a whole page (a plate, a cover): nothing past it
        box = (round(x0), round(y0), round(x1 - x0), round(y1 - y0))
        fx, fy, fw, fh = layout.picture_box(png, box, lines)
        for side, past in (
            ("top", y0 - fy),
            ("bottom", fy + fh - y1),
            ("left", x0 - fx),
            ("right", fx + fw - x1),
        ):
            if past > CUT * (high if side in ("top", "bottom") else wide):
                out.append(side)
    return list(dict.fromkeys(out))


def covered(b: Box, by: Sequence[Box]) -> float:
    """The share of `b` that the boxes `by` cover (overlaps counted once each, so at most an estimate when they overlap each other)."""
    area = max((b[2] - b[0]) * (b[3] - b[1]), 1e-6)
    got = sum(max(0.0, min(b[2], o[2]) - max(b[0], o[0])) * max(0.0, min(b[3], o[3]) - max(b[1], o[1])) for o in by)
    return min(1.0, got / area)


def missing_pictures(page: Drawn, read: Sequence[Box]) -> int:
    """Pictures the read found (figures.py, or a person drew) that no drawn picture covers half of."""
    return sum(1 for b in read if covered(b, page.pictures) < 0.5)


def text_under_pictures(page: Drawn, text: Sequence[Box]) -> int:
    """Lines of the page's text with more than UNDER of them under a drawn picture: not a picture of the whole page, under its text as a
    searchable scan's is (a page made a picture is the `text` check's, pipeline.rebuild_picture)."""
    w, h = page.size[0] * page.k, page.size[1] * page.k
    parts = [b for b in page.pictures if (b[2] - b[0]) * (b[3] - b[1]) < 0.9 * w * h]
    return sum(1 for t in text if covered(t, parts) > UNDER)


def oversized(pdf: str, page: Drawn) -> list[str]:
    """The page's size and weight, in words, when over A4 or HEAVY."""
    out: list[str] = []
    w, h = sorted(page.size)
    if w > A4_PT[0] or h > A4_PT[1]:
        out.append(f"the page is {w / 72:.0f} by {h / 72:.0f} inches")
    weight = os.path.getsize(pdf)
    if weight > HEAVY:
        out.append(f"the page weighs {weight / 1e6:.0f} MB")
    return out


def look(pdf: str, png: str, scan_width: float, text: Sequence[Box], read: Sequence[Box]) -> list[str]:
    """Every fault of the module's list found on the rebuilt page, in words (empty: none). `text`: the page's lines of text (the layout's
    blocks, scan pixels); `read`: the pictures the read found."""
    page = drawn(pdf, scan_width)
    out: list[str] = []
    if n := uneven_weight(page):
        out.append(f"{n} lines have words set in uneven weights")
    if n := stray_words(page):
        out.append(f"{n} words are set at a size unlike their line's")
    if n := overlapping_words(page):
        out.append(f"{n} words lie over others")
    if sides := cut_short(page, png, text):
        out.append("a picture is cut short at its " + ", ".join(sides))
    if n := missing_pictures(page, read):
        out.append(f"{n} pictures the read found are not drawn")
    if n := text_under_pictures(page, text):
        out.append(f"{n} lines of text have a picture drawn over them")
    return out + oversized(pdf, page)
