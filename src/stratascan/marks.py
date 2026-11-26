"""What a page with no print holds, lifted off its paper: handwriting, a bookplate, a stamp or a pencilled shelf mark kept on white, the paper,
its stains and its foxing taken away (Jonathan, 2026-11-26: "remove the background so the handwriting only would be kept on white", erring
on the side of keeping what is there). And a photograph of the book itself (its spine, its edges, its covers) trimmed to the book.

The paper is taken out twice over. Its tone, page by page: each pixel over the lightest paper near it, so a page darker at one edge or browned
in a patch comes out white. Its colour, book by book (`paper_hue`): a stain or foxing is the paper's own colour made darker and stronger,
where ink and pencil are grey or black and a printed bookplate red or blue, so a mark in the paper's colour that is more colour than dark is
taken for a stain. The book's text pages, mostly paper, tell its paper's colour (Jonathan: "use the colour of the ignored background on
text pages")."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

npa: Any = np  # numpy overloads are partially unknown to pyright: arrays here are Any
cv: Any = cv2  # and OpenCV's, given arrays of unknown type

EDGE = 0.02  # share of the page's shorter side at each edge left out: the leaf's own edge and the shadow of the board, never a mark
SEED = 60  # darkness (0-255, after the paper is taken out) a mark reaches somewhere: ink, pencil pressed down, a stamp
FAINT = 22  # darkness a mark's faint strokes reach, kept when joined to a SEED
COLOURED = 70  # colour (max - min channel) that counts as a seed on its own: a red stamp is light but strongly coloured
FAINT_COLOUR = 35
STAIN = 0.3  # a mark whose colour is above this share of its darkness, in the paper's own hue, is a stain or foxing
HUE_BELOW, HUE_ABOVE = (
    4,
    12,
)  # the hues (OpenCV, 0-180) taken for the paper's: a stain browns it, towards orange-yellow from a cream
WRITING = 0.012  # share of the page's width a cluster of marks spans to be kept: a word, a signature, a shelf mark; not a lone speck
CLUSTER = (
    0.015  # share of the page's width between marks that are one cluster (the letters of a word, the words of a line)
)
PATTERN = 0.2  # share of a page that is marks above which it is a pattern (marbled paper), kept whole
PLAIN = 25  # spread (standard deviation, 0-255) of a scan's edge within which it is one backdrop colour
PHOTO = 110  # median grey (0-255) of a page under which it is the book photographed (cloth, a spine), not paper
BACKDROP = 40  # colour distance from the backdrop at which the book begins, in a photograph of it


@dataclass
class Marks:
    image: Any  # the page in RGB, white but for its marks (uint8, h x w x 3)
    share: float  # the share of the page that is marks
    box: tuple[int, int, int, int] | None  # (x, y, w, h) round the marks, None when there are none


def paper_hue(pngs: Iterable[str]) -> float | None:
    """The hue (OpenCV, 0-180) of the book's paper: the median over the lighter part of each of its text pages; None with none to look at."""
    hues: list[float] = []
    for png in pngs:
        img = cv.imread(png)
        if img is None:
            continue
        hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
        light = hsv[..., 2] > npa.percentile(hsv[..., 2], 60)
        if light.any():
            hues.append(float(npa.median(hsv[..., 0][light])))
    return float(npa.median(hues)) if hues else None


def flatten(img: Any) -> Any:
    """Each pixel over the lightest paper near it (float32, 255 for paper), so the page's own tone, light and dark, is taken out."""
    high, wide = img.shape[:2]
    small = cv.resize(img, (max(1, wide // 4), max(1, high // 4)), interpolation=cv.INTER_AREA)
    k = (
        max(3, min(high, wide) // 160) | 1
    )  # wider than a pen stroke at a quarter size, narrower than a stain's change of tone
    paper = cv.medianBlur(cv.dilate(small, npa.ones((k, k), npa.uint8)), k)
    paper = cv.resize(paper, (wide, high), interpolation=cv.INTER_LINEAR).astype(npa.float32)
    return npa.clip(img.astype(npa.float32) / npa.maximum(paper, 1.0) * 255.0, 0, 255)


def lift(png: str, hue: float | None) -> Marks:
    """The page's marks on white (`Marks`). `hue`: the book's paper (`paper_hue`); None keeps every mark, stains too."""
    bgr = cv.imread(png)
    if bgr is None:
        raise ValueError(f"cannot read {png}")
    high, wide = bgr.shape[:2]
    flat = flatten(bgr)
    dark = 255.0 - flat.min(axis=2)
    colour = flat.max(axis=2) - flat.min(axis=2)
    inner = npa.zeros((high, wide), bool)
    m = int(EDGE * min(high, wide))
    inner[m : high - m, m : wide - m] = True
    seed = ((dark > SEED) | (colour > COLOURED)) & inner
    faint = ((dark > FAINT) | (colour > FAINT_COLOUR)) & inner
    n, lab, stats, _ = cv.connectedComponentsWithStats(faint.astype(npa.uint8), connectivity=8)
    keep = npa.bincount(lab[seed], minlength=n) >= max(
        20, high * wide // 400_000
    )  # a seed of some size, not one stray pixel
    keep[0] = False
    hues = cv.cvtColor(bgr, cv.COLOR_BGR2HSV)[..., 0].astype(npa.float32)
    boxes: dict[int, list[int]] = {}
    for i in npa.flatnonzero(keep):
        x, y, w, h = (int(v) for v in stats[i, :4])
        part = lab[y : y + h, x : x + w] == i
        d = float(dark[y : y + h, x : x + w][part].mean())
        c = float(colour[y : y + h, x : x + w][part].mean())
        off = float(npa.median(hues[y : y + h, x : x + w][part])) - hue if hue is not None else None
        if off is not None and c > STAIN * d and -HUE_BELOW <= off <= HUE_ABOVE:
            keep[i] = False  # the paper's colour, darker: a stain, foxing, old tape
            continue
        boxes[int(i)] = [x, y, x + w, y + h]
    for ids, (x0, y0, x1, y1) in clusters(boxes, CLUSTER * wide):
        if max(x1 - x0, y1 - y0) < WRITING * wide:
            keep[ids] = False
    ink = keep[lab]
    ink = cv.dilate(ink.astype(npa.uint8), npa.ones((5, 5), npa.uint8)).astype(
        bool
    )  # the soft edge of each stroke with it
    out = npa.full((high, wide, 3), 255, npa.uint8)
    out[ink] = flat[ink][:, ::-1].astype(npa.uint8)  # BGR to RGB
    ys, xs = npa.nonzero(ink)
    box = (int(xs.min()), int(ys.min()), int(npa.ptp(xs)) + 1, int(npa.ptp(ys)) + 1) if len(xs) else None
    return Marks(out, float(ink.mean()), box)


def save(marks: Marks, out: str) -> str:
    """The part of the page round its marks (`Marks.box`) written to `out`; its path."""
    if marks.box is None:
        raise ValueError("no marks to save")
    x, y, w, h = marks.box
    cv.imwrite(out, cv.cvtColor(marks.image[y : y + h, x : x + w], cv.COLOR_RGB2BGR))
    return out


def clusters(boxes: dict[int, list[int]], near: float) -> list[tuple[list[int], tuple[int, int, int, int]]]:
    """The boxes (x0, y0, x1, y1) within `near` of each other gathered: (their ids, the box round them all)."""
    ids = list(boxes)
    parent = {i: i for i in ids}

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a in range(len(ids)):
        p = boxes[ids[a]]
        for b in range(a + 1, len(ids)):
            q = boxes[ids[b]]
            if p[0] < q[2] + near and q[0] < p[2] + near and p[1] < q[3] + near and q[1] < p[3] + near:
                parent[root(ids[a])] = root(ids[b])
    groups: dict[int, list[int]] = {}
    for i in ids:
        groups.setdefault(root(i), []).append(i)
    out: list[tuple[list[int], tuple[int, int, int, int]]] = []
    for members in groups.values():
        bs = [boxes[i] for i in members]
        out.append(
            (members, (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)))
        )
    return out


def backdrop(img: Any) -> Any | None:
    """The colour (BGR) the book was photographed on: the median of the scan's outer edge; None when that edge is not one plain colour (a
    scan cut to the page, a library's copy with no backdrop round it), so there is nothing to trim."""
    high, wide = img.shape[:2]
    m = max(1, min(high, wide) // 100)
    edge = npa.concatenate(
        [img[:m].reshape(-1, 3), img[-m:].reshape(-1, 3), img[:, :m].reshape(-1, 3), img[:, -m:].reshape(-1, 3)]
    )
    if float(edge.std(axis=0).mean()) > PLAIN:
        return None
    return npa.median(edge, axis=0)


def dark(png: str) -> bool:
    """Whether the page is a photograph of the book rather than a leaf of it: mostly darker than any paper (its spine, its cloth)."""
    img = cv.imread(png, cv.IMREAD_GRAYSCALE)
    return img is not None and float(npa.median(img)) < PHOTO


def book_box(img: Any, behind: Any | None) -> tuple[int, int, int, int] | None:
    """(x, y, w, h) of the book in a photograph of it on `behind` (`backdrop`): the largest thing unlike the backdrop; None when the
    photograph is all book (nothing to trim)."""
    if behind is None:
        return None
    high, wide = img.shape[:2]
    far = npa.linalg.norm(img.astype(npa.float32) - npa.asarray(behind, npa.float32), axis=2) > BACKDROP
    k = max(3, min(high, wide) // 100) | 1
    far = cv.morphologyEx(
        far.astype(npa.uint8), cv.MORPH_OPEN, npa.ones((k, k), npa.uint8)
    )  # specks of dust on the backdrop
    far = cv.morphologyEx(
        far, cv.MORPH_CLOSE, npa.ones((k, k), npa.uint8)
    )  # the book's own dark patches (its cloth, gilding)
    n, _, stats, _ = cv.connectedComponentsWithStats(far, connectivity=8)
    if n < 2:
        return None
    i = 1 + int(npa.argmax(stats[1:, cv.CC_STAT_AREA]))
    x, y, w, h = (int(v) for v in stats[i, :4])
    if w * h > 0.97 * wide * high:
        return None
    return x, y, w, h
