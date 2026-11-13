"""Where the page is in a scan, and how much it leans: the automatic first guess at a page's rotation and crop, which a person can then correct.

Learned from diary-study (document_finder.py, image_enhancer.py), cut down for printed books. The two books this was built on show the two
cases: an Internet Archive scan of an 1828 book on a dark scanner bed, tilted a degree or so with the neighbouring page's edges along the
gutter, and an 1874 pamphlet already cut to its page. So:

1. Page against background (`find_page`): Otsu threshold on a blurred, shrunk grey picture, opened so text and thin bright edges do not join
   the page to the margin, then the largest light region. If it covers nearly everything there is no background and the page is the whole
   scan. Its minimum-area rectangle gives the first angle.
2. Trim (`_trim`): in the picture turned by that angle, rows and columns that are less than `FILL` page are cut from each side: the stack of
   page edges at the gutter and the bed's shadows are light but patchy, the page itself is solid.
2b. A light region under a quarter of the scan is a label on a dark cover, not a page: the scan is kept whole, at confidence 0.2.
3. Lean of the type (`text_skew`): the projection-profile method. The sharpest row profile of the dark pixels over -3..3 degrees is the angle
   at which the text lines are level; it is finer than the page's outline, which is cut and bent by hand. Added to the outline's angle, and
   only trusted when the page has text (a contrast test), so an engraving is not "straightened" by its hatching.
4. Spreads (`split_spread`): a page region wider than it is tall holds two pages; the fold is the darkest column band in the middle third
   (diary-study's smart split, a projection of a vertical-edge filter, simplified to a brightness valley, which is what a book's gutter is).

Angles are degrees counter-clockwise, as OpenCV's `getRotationMatrix2D` takes them; a page is the scan turned by `angle` about its centre
with the canvas grown to hold it all (`rotate`), then cut to `crop` (x, y, w, h in that turned picture)."""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]
WORK = 800  # long side of the shrunk picture the outline is found in: enough for a degree, fast on 4000 px scans
# Otsu's two classes closer than this (grey levels) are shades of one paper, not paper on a bed. Measured on both books: paper-only
# scans 13-20 (39 for a full page of type), covers on a bed 50-95, pages on a bed 125-135.
BED_CONTRAST = 30
FILL = 0.80  # a row or column that is less page than this is trimmed from the edge
FULL = 0.94
SMALL = 0.25  # a light region smaller than this share of the scan is not a page (a label on a dark cover)  # a light region covering this much of the scan means there is no background to cut


@dataclass(frozen=True)
class PageGuess:
    """One page found in a scan: the turn and the cut in full-size pixels, and how sure the finder is (0-1)."""

    angle: float
    crop: tuple[int, int, int, int]
    confidence: float
    side: str = "single"  # single, left or right (the halves of a spread)


def u8(a: object) -> Image:
    """An OpenCV result as the uint8 array it is (cv2's stubs type every result as the wide MatLike)."""
    return np.asarray(a, dtype=np.uint8)


def argbest(values: list[float], lowest: bool = False) -> int:
    return (
        min(range(len(values)), key=values.__getitem__) if lowest else max(range(len(values)), key=values.__getitem__)
    )


def gray(img: Image) -> Image:
    return img if img.ndim == 2 else np.asarray(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), dtype=np.uint8)


def rotate(img: Image, angle: float, fill: tuple[int, int, int] = (255, 255, 255)) -> Image:
    """`img` turned `angle` degrees counter-clockwise about its centre, the canvas grown so no corner is lost (new corners white)."""
    if abs(angle) < 1e-6:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    c, s = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = round(h * s + w * c), round(h * c + w * s)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    border = fill if img.ndim == 3 else fill[0]
    return np.asarray(
        cv2.warpAffine(img, m, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=border),
        dtype=np.uint8,
    )


def rotated_size(w: int, h: int, angle: float) -> tuple[int, int]:
    """The size `rotate` gives a w x h picture."""
    if abs(angle) < 1e-6:
        return w, h
    a = np.deg2rad(angle)
    c, s = abs(float(np.cos(a))), abs(float(np.sin(a)))
    return round(h * s + w * c), round(h * c + w * s)


def apply(img: Image, angle: float, crop: tuple[int, int, int, int]) -> Image:
    """The page: `img` turned by `angle`, cut to `crop` (clamped to the turned picture)."""
    r = rotate(img, angle)
    x, y, w, h = clamp(crop, r.shape[1], r.shape[0])
    return np.ascontiguousarray(r[y : y + h, x : x + w])


def clamp(crop: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int]:
    x, y, cw, ch = crop
    x, y = max(0, min(int(x), w - 1)), max(0, min(int(y), h - 1))
    return x, y, max(1, min(int(cw), w - x)), max(1, min(int(ch), h - y))


def _page_mask(small: Image) -> Image:
    g = cv2.GaussianBlur(gray(small), (5, 5), 0)
    t, m = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark, light = g[g <= t], g[g > t]
    if (
        light.size == 0 or dark.size == 0
    ):  # one flat shade (an empty scan): nothing to go on, which find_page says with 0.5
        return np.zeros(g.shape, dtype=np.uint8) if light.size == 0 else np.full(g.shape, 255, dtype=np.uint8)
    if float(light.mean()) - float(dark.mean()) < BED_CONTRAST:
        # no bed: the scan is all paper, and Otsu only split its shades (bleed-through, foxing), which cut blank pages to a patch
        return np.full(g.shape, 255, dtype=np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)  # text and rules inside the page
    return np.asarray(cv2.morphologyEx(m, cv2.MORPH_OPEN, k), dtype=np.uint8)  # thin bright edges and specks outside it


def _largest(mask: Image) -> Image | None:
    """The largest light region, joined by any other at least half its size: the two pages of a spread whose gutter shadow is dark
    enough to cut them apart in the mask are still one region to turn and trim, and `find_pages` splits them again at the fold."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    if n <= 1:
        return None
    areas = [int(a) for a in np.asarray(stats, dtype=np.int64)[1:, cv2.CC_STAT_AREA]]
    keep = [1 + i for i, a in enumerate(areas) if a >= 0.5 * max(areas)]
    lab = np.asarray(labels, dtype=np.int64)
    joined = u8(np.zeros(lab.shape, dtype=np.uint8))
    for k in keep:
        joined[lab == k] = 255
    if len(keep) > 1:  # fill the gap between them, so the region is one shape for minAreaRect and the trim
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, mask.shape[1] // 20), 3))
        joined = cv2.morphologyEx(joined, cv2.MORPH_CLOSE, k)
    return np.asarray(joined, dtype=np.uint8)


def _trim(mask: Image) -> tuple[int, int, int, int]:
    """The box left after cutting rows and columns that are less than FILL page from each side of `mask`'s bounding box."""
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    for _ in range(3):  # cutting rows changes the columns' fill and back; two or three rounds settle it
        sub = mask[y0:y1, x0:x1] > 0
        cols, rows = sub.mean(axis=0), sub.mean(axis=1)
        good_c, good_r = np.nonzero(cols >= FILL)[0], np.nonzero(rows >= FILL)[0]
        if len(good_c) == 0 or len(good_r) == 0:
            break
        nx0, nx1, ny0, ny1 = (
            x0 + int(good_c[0]),
            x0 + int(good_c[-1]) + 1,
            y0 + int(good_r[0]),
            y0 + int(good_r[-1]) + 1,
        )
        if (nx0, nx1, ny0, ny1) == (x0, x1, y0, y1):
            break
        x0, x1, y0, y1 = nx0, nx1, ny0, ny1
    return x0, y0, x1 - x0, y1 - y0


def text_skew(page: Image, limit: float = 3.0, step: float = 0.1) -> float | None:
    """The angle (degrees, counter-clockwise) that levels the page's lines of type, or None when the page has too little text to say. A
    coarse pass in half degrees, then `step` around the best; the score is the variance of the row sums of dark pixels."""
    g = gray(page)
    scale = 1000 / max(g.shape)
    if scale < 1:
        g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = g.shape
    g = g[
        int(h * 0.06) : int(h * 0.94), int(w * 0.08) : int(w * 0.92)
    ]  # margins hold the page edge and the gutter shadow, not type
    ink = u8(cv2.adaptiveThreshold(g, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15))
    if ink.mean() < 0.01:
        return None

    def score(a: float) -> float:
        r = rotate(ink, a, fill=(0, 0, 0))
        return float(np.var(r.sum(axis=1, dtype=np.float64)))

    coarse = [float(a) for a in np.arange(-limit, limit + 1e-9, 0.5)]
    scores = [score(a) for a in coarse]
    best = coarse[argbest(scores)]
    # lines of type give one peak that falls away on both sides; pictures and scattered words give a flat or one-sided curve. (Not "peak
    # over median": with widely spaced lines the peak is broad and a page tilted 1° failed that.)
    if max(scores) < 1.5 * min(scores) or best in (coarse[0], coarse[-1]):
        return None
    fine = [float(a) for a in np.arange(best - 0.5, best + 0.5 + 1e-9, step)]
    return round(fine[argbest([score(a) for a in fine])], 2)


def find_page(img: Image) -> PageGuess:
    """The page in a scan (or the bigger one, if the region holds a spread: see `find_pages`)."""
    h, w = img.shape[:2]
    scale = min(1.0, WORK / max(h, w))
    small = u8(cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)) if scale < 1 else img
    region = _largest(_page_mask(small))
    if region is not None and (region > 0).mean() < SMALL:
        # a dark cover on a dark bed: the light region is a label or a stamp, not the page. Say so with a low confidence and keep the scan
        # whole, which a person corrects in one drag; cutting to the label would hide the cover.
        return PageGuess(0.0, (0, 0, w, h), 0.2)
    if region is None or (region > 0).mean() >= FULL:
        angle = text_skew(img) or 0.0
        rw, rh = rotated_size(w, h, angle)
        mx, my = (rw - w) // 2, (rh - h) // 2  # the scan is the page: cut back to its own size, not the grown canvas
        return PageGuess(angle, clamp((mx, my, w, h), rw, rh), 0.5 if region is None else 0.9)
    cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    points = np.asarray(
        [pt for c in cnts for pt in np.asarray(c, dtype=np.int32).reshape(-1, 2).tolist()], dtype=np.int32
    )
    _, _, a = cv2.minAreaRect(points)
    # OpenCV's box angle convention changed between versions ([-90, 0) before 4.5, (0, 90] after); either way the page's lean is the
    # equivalent angle nearest zero. Its y axis points down, so a positive angle is a clockwise lean, which getRotationMatrix2D undoes
    # with the same positive number.
    lean = float((a + 45) % 90 - 45)
    turned = rotate(region, lean, fill=(0, 0, 0))
    _, turned = cv2.threshold(turned, 127, 255, cv2.THRESH_BINARY)
    x, y, cw, ch = _trim(np.asarray(turned, dtype=np.uint8))
    fill = float((turned[y : y + ch, x : x + cw] > 0).mean())
    # back to full size: the turned small picture and the turned full one share their centre, so scale about it
    sw, sh = turned.shape[1], turned.shape[0]
    fw, fh = rotated_size(w, h, lean)
    fx, fy = fw / sw, fh / sh
    crop = (round(x * fx), round(y * fy), round(cw * fx), round(ch * fy))
    page = apply(img, lean, crop)
    extra = text_skew(page)
    if extra is not None and abs(extra) > 0.05:
        angle = lean + extra
        # the cut stays centred on the same point of the page; its size stays the same (a fraction of a degree changes it by a few pixels)
        cx, cy = crop[0] + crop[2] / 2 - fw / 2, crop[1] + crop[3] / 2 - fh / 2
        t = np.deg2rad(extra)
        ncx, ncy = cx * np.cos(t) + cy * np.sin(t), -cx * np.sin(t) + cy * np.cos(t)
        nw, nh = rotated_size(w, h, angle)
        crop = (round(nw / 2 + ncx - crop[2] / 2), round(nh / 2 + ncy - crop[3] / 2), crop[2], crop[3])
        crop = clamp(crop, nw, nh)
    else:
        angle = lean
    return PageGuess(round(angle, 2), crop, round(min(1.0, fill), 2))


def gutter(page: Image) -> int | None:
    """The column of a spread's fold: the darkest band of the middle third (column means of a blurred grey picture), or None when there is no
    clear valley (it must be darker than both quarters beside it)."""
    g = gray(page)
    small = cv2.resize(g, (400, max(1, int(400 * g.shape[0] / g.shape[1]))), interpolation=cv2.INTER_AREA)
    cols = np.asarray(
        cv2.GaussianBlur(np.asarray(small, dtype=np.float32).mean(axis=0).reshape(1, -1), (1, 9), 0), dtype=np.float32
    ).ravel()
    lo, hi = int(len(cols) / 3), int(2 * len(cols) / 3)
    i = lo + argbest([float(c) for c in cols[lo:hi]], lowest=True)
    side = min(float(np.median(cols[: len(cols) // 4])), float(np.median(cols[3 * len(cols) // 4 :])))
    if float(cols[i]) > side - 12:
        return None
    return round(i * g.shape[1] / 400)


def find_pages(img: Image) -> list[PageGuess]:
    """The pages in a scan: one, or the two halves of a spread (a page region at least 1.15 times wider than tall with a gutter)."""
    p = find_page(img)
    x, y, w, h = p.crop
    if w < 1.15 * h:
        return [p]
    g = gutter(apply(img, p.angle, p.crop))
    if g is None:
        return [p]
    return [
        PageGuess(p.angle, (x, y, g, h), p.confidence, "left"),
        PageGuess(p.angle, (x + g, y, w - g, h), p.confidence, "right"),
    ]
