"""Pictures on a page (engravings, diagrams, ornaments): the boxes of what is ink but not text, as a first guess a person corrects.

The OCR has already said where the words are, so a picture is what is left: dark pixels (adaptive threshold, so yellowed paper and the gutter
shadow are not ink) minus the words Tesseract was sure of. Tesseract also "reads" engravings, as runs of low-confidence nonsense, so only
words at `WORD_CONF` or more are taken out: a picture keeps its nonsense words and stays whole. Long straight rules (a printed border round
every page of the 1874 book, rules under running heads) are removed by opening with long thin kernels, or the border would join everything
into one page-sized "picture". What remains is closed with a kernel of about 1.5% of the page, so the strokes of one engraving join; a
region is a picture if it is big enough (`MIN_AREA` of the page, `MIN_SIDE` on each side) and dense enough (`MIN_INK` of its box is ink: a
few stray marks spread over a margin are not)."""

import cv2
import numpy as np
from numpy.typing import NDArray

from stratascan.geometry import Image, gray

WORD_CONF = 60.0
MIN_AREA = 0.015
MIN_SIDE = 0.06
MIN_INK = 0.06
Box = tuple[int, int, int, int]


def ink(page: Image) -> NDArray[np.uint8]:
    g = gray(page)
    block = max(15, (min(g.shape) // 60) | 1)  # odd, about a line's height
    return np.asarray(
        cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 20), dtype=np.uint8
    )


def without_rules(m: NDArray[np.uint8]) -> NDArray[np.uint8]:
    h, w = m.shape
    lines = np.zeros_like(m)
    for k in ((max(40, w // 6), 1), (1, max(40, h // 6))):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, k)
        lines |= np.asarray(
            cv2.dilate(cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel), np.ones((5, 5), np.uint8)), dtype=np.uint8
        )
    return np.asarray(m & ~lines, dtype=np.uint8)


def find_figures(page: Image, words: list[tuple[Box, float]]) -> list[Box]:
    """Boxes (x, y, w, h in the page's pixels) of the pictures on `page`, top to bottom. `words` are the OCR's word boxes and confidences."""
    h, w = page.shape[:2]
    m = without_rules(ink(page))
    pad = max(2, h // 400)
    for (x, y, bw, bh), conf in words:
        if conf >= WORD_CONF:
            m[max(0, y - pad) : y + bh + pad, max(0, x - pad) : x + bw + pad] = 0
    k = max(9, int(min(h, w) * 0.015))
    joined = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out: list[Box] = []
    for i in range(1, n):
        x, y, bw, bh, _ = (int(v) for v in stats[i])
        if bw * bh < MIN_AREA * w * h or bw < MIN_SIDE * w or bh < MIN_SIDE * h:
            continue
        if float((m[y : y + bh, x : x + bw] > 0).mean()) < MIN_INK:
            continue
        out.append((x, y, bw, bh))
    return merge(sorted(out, key=lambda b: (b[1], b[0])))


def merge(boxes: list[Box]) -> list[Box]:
    """Boxes that overlap become one (a caption's ornament inside its picture, two halves of one engraving)."""
    out = list(boxes)
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                if a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]:
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
                    out[i] = (x0, y0, x1 - x0, y1 - y0)
                    del out[j]
                    changed = True
                    break
            if changed:
                break
    return out


def pad_box(box: Box, w: int, h: int, share: float = 0.01) -> Box:
    """A little paper round a picture, so its edge strokes are not cut."""
    p = round(max(w, h) * share)
    x0, y0 = max(0, box[0] - p), max(0, box[1] - p)
    x1, y1 = min(w, box[0] + box[2] + p), min(h, box[1] + box[3] + p)
    return x0, y0, x1 - x0, y1 - y0
