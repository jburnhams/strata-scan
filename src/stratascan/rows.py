"""The printed rows of a text page found from its ink, and the OCR's lines put right by them: Tesseract skips whole lines of display type (an
advert's "PAPERHANGINGS") and boxes others with the page's frame or a neighbouring row, so a page set in type from its lines lacks a line the
corrected text has, or sets one at twice its size. The corrected text keeps the print's line breaks, so each of its lines is one of the rows
(2026-11-25: 20 rows and 20 lines, 24 and 24, 21 and 21, 23 and 23 on four adverts of the 1874 book): `repair` pairs them in order, and where
the OCR has no good line on a row, gives the row its text there. Nothing is asked of a model.

A row the OCR read well keeps the OCR's line as it is, so a page it reads well is left alone."""

import itertools
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, cast

import cv2
import numpy as np

from stratascan import gate
from stratascan.align import likeness

Box = tuple[int, int, int, int]  # x, y, width, height in the page's pixels

SPECK = 1 / 20000  # of a square inch: a smaller mark is dust
RULE_WIDE, RULE_THIN = 0.18, 0.02  # of the page: a mark this wide and this flat (and 8 times wider than high) is a rule
TALL, BROAD = 0.12, 0.5  # of the page: a larger mark is the frame or a picture
FRAME = 0.25  # of the page's height: a column with a vertical line this long is the frame's
LETTER = 0.8, 0.4  # of the row's height and width: a mark this big is a letter, and some word's box must hold it
MARK = 3  # glyphs a row needs to be type: an ornament or a stray mark has fewer
SKIP = 0.35  # what leaving a row or a line unpaired costs, against a pair's likeness of 0 to 1
GOOD = (
    0.85,
    0.75,
)  # of a line's box that must lie in the row's, and of the row's that must lie in it, for it to be a good line


@dataclass(frozen=True)
class Row:
    box: Box
    glyphs: tuple[Box, ...]  # left to right


def ink_glyphs(gray: gate.Gray, dpi: float) -> list[Box]:
    """The page's marks that can be type: not specks, rules, the frame or pictures."""
    ink = gate.ink_of(gray, dpi).astype(np.uint8)
    high, wide = ink.shape
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    left, right = frame(ink)
    out: list[Box] = []
    for x, y, w, h, area in cast("list[list[int]]", stats[1:].tolist()):
        if area < max(12.0, dpi * dpi * SPECK):
            continue
        if w > RULE_WIDE * wide and h < RULE_THIN * high and w > 8 * h:
            continue
        if h > TALL * high or w > BROAD * wide or (h > 6 * w and h > 0.03 * high):
            continue
        if x >= left - 4 and x + w <= right + 4:
            out.append((x, y, w, h))
    return out


def frame(ink: Any) -> tuple[int, int]:
    """(left, right) inside the printed frame's vertical lines; the page's edges when there are none."""
    high, wide = ink.shape
    upright = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, int(0.03 * high))))
    lines = cv2.morphologyEx(cv2.dilate(ink, np.ones((1, 7), np.uint8)), cv2.MORPH_OPEN, upright)
    at = [int(c) for c in np.nonzero(lines.sum(0) > FRAME * high)[0]]
    left, right = [c for c in at if c < wide / 2], [c for c in at if c > wide / 2]
    return (max(left) + 12 if left else 0), (min(right) - 12 if right else wide)


def find_rows(gray: gate.Gray, dpi: float) -> list[Row]:
    """The page's rows of type, top to bottom. A glyph joins the row its middle falls in; the tallest start the rows."""
    marks = ink_glyphs(gray, dpi)
    if not marks:
        return []
    usual = float(np.median([b[3] for b in marks]))
    rows: list[list[Box]] = []
    for b in sorted((b for b in marks if b[3] >= 0.45 * usual), key=lambda b: -b[3]):
        middle = b[1] + b[3] / 2
        # the first glyph is the row's tallest
        fits = [r for r in rows if r[0][1] <= middle <= r[0][1] + r[0][3]]
        if fits:
            min(fits, key=lambda r: abs(middle - (r[0][1] + r[0][3] / 2))).append(b)
        else:
            rows.append([b])
    out: list[Row] = []
    for r in rows:
        if len(r) < MARK:
            continue
        x0, y0 = min(b[0] for b in r), min(b[1] for b in r)
        x1, y1 = max(b[0] + b[2] for b in r), max(b[1] + b[3] for b in r)
        out.append(Row((x0, y0, x1 - x0, y1 - y0), tuple(sorted(r))))
    return sorted(out, key=lambda r: r.box[1] + r.box[3] / 2)


def _share(a: Box, b: Box) -> float:
    """How much of `a` lies in `b`."""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h) / max(1, a[2] * a[3])


def _letters(s: str) -> int:
    return sum(c.isalnum() for c in s)


def pair_rows(rows: list[Row], texts: list[str], read: list[str]) -> list[int | None]:
    """For each row, the index of the line of `texts` it is, in order: by likeness to what the OCR read there (`read`, "" when nothing) and by
    how many glyphs it holds. Two rows never take one line; a row or a line left over costs SKIP."""

    def worth(i: int, j: int) -> float:
        n, want = len(rows[i].glyphs), max(1, _letters(texts[j]))
        size = max(0.0, 1.0 - abs(float(np.log(max(1, n) / want))))
        return 0.75 * likeness(read[i], texts[j]) + 0.25 * size if read[i] else 0.6 * size

    n, m = len(rows), len(texts)
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best[i][j] = max(best[i + 1][j], best[i][j + 1], worth(i, j) + best[i + 1][j + 1])
    out: list[int | None] = []
    i = j = 0
    while i < n:
        if j < m and worth(i, j) > 0 and best[i][j] == worth(i, j) + best[i + 1][j + 1] and worth(i, j) >= SKIP:
            out.append(j)
            i, j = i + 1, j + 1
        elif j < m and best[i][j] == best[i][j + 1]:
            j += 1
        else:
            out.append(None)
            i += 1
    # between two sure pairs, as many rows as lines left over are each other: hollow display letters break into many marks, so a row's glyphs
    # say little of its letters there
    ends = [-1, *[k for k, v in enumerate(out) if v is not None], n]
    for a, b in itertools.pairwise(ends):
        first = cast("int", out[a]) + 1 if a >= 0 else 0
        last = cast("int", out[b]) if b < n else m
        if b - a - 1 == last - first:
            for k in range(b - a - 1):
                out[a + 1 + k] = first + k
    return out


def split_words(row: Row, text: str) -> list[dict[str, Any]]:
    """The row's glyphs cut into the text's words, each with its box: the cuts that fall in wide gaps and give each word a width near its share
    of the letters. Fewer glyph groups than words: one box a word, in proportion to its letters."""
    parts = text.split()
    groups: list[list[int]] = []  # [left, right] of the glyphs that overlap in x
    for x, _, w, _ in row.glyphs:
        if groups and x <= groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], x + w)
        else:
            groups.append([x, x + w])
    x0, y0, wide, h = row.box
    n, k = len(groups), len(parts)
    total = sum(max(1, len(p)) for p in parts) + k - 1
    share = [max(1, len(p)) / total for p in parts]
    if n < k:
        at, boxes = float(x0), list[dict[str, Any]]()
        for p, f in zip(parts, share, strict=True):
            boxes.append({"text": p, "box": [int(at), y0, int(wide * f), h], "conf": 90.0})
            at += wide * f + wide / total
        return boxes

    def cost(a: int, b: int, word: int) -> float:
        """Of the word `word` being groups a to b-1, with the gap before it."""
        width = (groups[b - 1][1] - groups[a][0]) / wide
        gap = (groups[a][0] - groups[a - 1][1]) / h if a else 1.0
        return 6.0 * abs(width - share[word]) - min(gap, 1.0)

    far = float("inf")
    best = [[far] * (n + 1) for _ in range(k + 1)]
    back = [[0] * (n + 1) for _ in range(k + 1)]
    best[0][0] = 0.0
    for word in range(1, k + 1):
        for b in range(word, n + 1):
            for a in range(word - 1, b):
                if best[word - 1][a] < far:
                    c = best[word - 1][a] + cost(a, b, word - 1)
                    if c < best[word][b]:
                        best[word][b], back[word][b] = c, a
    cuts, b = [n], n
    for word in range(k, 0, -1):
        b = back[word][b]
        cuts.append(b)
    cuts.reverse()
    out: list[dict[str, Any]] = []
    for p, a, b in zip(parts, cuts, cuts[1:], strict=False):
        left, right = groups[a][0], groups[b - 1][1]
        inside = [g for g in row.glyphs if left <= g[0] < right]
        top, low = min(g[1] for g in inside), max(g[1] + g[3] for g in inside)
        out.append({"text": p, "box": [left, top, right - left, low - top], "conf": 90.0})
    return out


def tidy(ocr: dict[str, Any], gray: gate.Gray, dpi: float) -> dict[str, Any]:
    """The OCR answer with each line's words kept to the row it stands on: a word that is no word and lies outside the row (the page's frame read
    as "|") goes, and a box that runs into the frame, or over a neighbouring row, is cut to the row. The lines and their numbers stay, so a
    layout read from them still holds."""
    rows = find_rows(gray, dpi)
    out: list[dict[str, Any]] = []
    for ln in cast("list[dict[str, Any]]", ocr.get("lines") or []):
        ly, lh = int(ln["box"][1]), int(ln["box"][3])
        row = next((r for r in rows if r.box[1] <= ly + lh / 2 <= r.box[1] + r.box[3]), None)
        words = cast("list[dict[str, Any]]", ln.get("words") or [])
        if row is None or not words:
            out.append(ln)
            continue
        x0, y0, x1, y1 = row.box[0], row.box[1], row.box[0] + row.box[2], row.box[1] + row.box[3]
        kept: list[dict[str, Any]] = []
        for w in words:
            x, y, bw, bh = (int(v) for v in w["box"])
            outside = x + bw <= x0 or x >= x1
            if outside and not re.search(r"\w", str(w["text"])):
                continue
            slack = 0.6 * row.box[3]  # a stop or a comma is no glyph of the row's
            left = x0 if x < x0 - slack and not outside else x
            right = x1 if x + bw > x1 + slack and not outside else x + bw
            top, low = (max(y, y0 - 2), min(y + bh, y1 + 2)) if bh > 1.3 * row.box[3] else (y, y + bh)
            kept.append(dict(w, box=[left, top, right - left, low - top]) if right > left and low > top else w)
        if kept != words and kept:
            a, c = min(w["box"][0] for w in kept), max(w["box"][0] + w["box"][2] for w in kept)
            text = " ".join(str(w["text"]) for w in kept) if len(kept) != len(words) else str(ln["text"])
            # the line's height stays: strata-models splits a line where its words stand further apart than so many heights
            ln = dict(ln, words=kept, box=[a, ly, c - a, lh], text=text)
        out.append(ln)
    return dict(ocr, lines=out)


def picture_mark(word: str) -> bool:
    """A word that is a picture and not type, such as a pointing hand: no text face has it, so it is cut from the scan."""
    return bool(word) and all(unicodedata.category(c) == "So" for c in word)


def repair(ocr: dict[str, Any], gray: gate.Gray, text: str, dpi: float) -> tuple[dict[str, Any], int]:
    """(the OCR answer with its missing and badly boxed lines put right, how many lines that changed). `text` is the page's corrected text. The
    answer itself when there is nothing to do, or when the text's lines are not the page's rows. A line the OCR read on its row stays as it
    is: the words of a justified line cannot be cut as well as the OCR cut them (2026-11-25: dialogue pages it read well came out worse)."""
    texts = [ln.strip() for ln in text.splitlines() if _letters(ln) > 1]  # a lone letter is an ornament read as type
    rows = find_rows(gray, dpi)
    lines = cast("list[dict[str, Any]]", ocr.get("lines") or [])
    if not rows or not texts:
        return ocr, 0
    boxes = [cast("Box", tuple(int(v) for v in ln["box"])) for ln in lines]

    def on(r: Row) -> list[int]:
        """The OCR lines whose middle lies in the row, or that cover half of it."""
        return [
            k
            for k, b in enumerate(boxes)
            if r.box[1] <= b[1] + b[3] / 2 <= r.box[1] + r.box[3] or _share(r.box, b) > 0.5
        ]

    near = [on(r) for r in rows]
    read = [" ".join(str(lines[k]["text"]) for k in ks) for ks in near]
    where = pair_rows(rows, texts, read)
    done = [(i, j) for i, j in enumerate(where) if j is not None]
    if len(done) < 0.8 * min(len(rows), len(texts)):
        return ocr, 0  # the text's lines are not the rows: a page of two columns, say
    new: dict[int, dict[str, Any]] = {}
    drop: set[int] = set()
    pictures: list[list[int]] = []
    for i, j in done:
        if _letters(texts[j]) > 1.5 * len(rows[i].glyphs):
            continue  # more letters than the row holds: the text joined the print's lines
        if not bad_line(rows[i], [lines[k] for k in near[i]], [boxes[k] for k in near[i]], texts[j], read[i]):
            continue
        cut = split_words(rows[i], texts[j])
        pictures += [w["box"] for w in cut if picture_mark(str(w["text"]))]
        cut = [w for w in cut if not picture_mark(str(w["text"]))]
        new[i] = {
            "text": " ".join(str(w["text"]) for w in cut),
            "box": list(rows[i].box),
            "conf": 90.0,
            "block": 1000 + i,
            "words": cut,
        }
        drop.update(near[i])
    if not new:
        return ocr, 0
    # a line of two rows goes with whichever of its rows is put right; the others keep their own line only when they were good
    held = {k for i in set(range(len(rows))) - set(new) for k in near[i] if where[i] is not None and len(near[i]) == 1}
    drop -= {k for k in held if sum(k in ks for ks in near) == 1}
    kept = [(b[1] + b[3] / 2, 0, ln) for k, (b, ln) in enumerate(zip(boxes, lines, strict=True)) if k not in drop]
    added = [(ln["box"][1] + ln["box"][3] / 2, 1, ln) for ln in new.values()]
    out = [ln for _, _, ln in sorted(kept + added, key=lambda t: (t[0], t[1]))]
    out = [ln for ln in out if re.search(r"\w", str(ln["text"]))]
    return dict(
        ocr, lines=out, text="\n".join(str(ln["text"]) for ln in out), repaired=len(new), pictures=pictures
    ), len(new)


def bad_line(row: Row, mine: list[dict[str, Any]], boxes: list[Box], text: str, read: str) -> bool:
    """Whether the OCR has no good line on the row: none, several, one that runs out of the row (into the frame) or takes in another, one that
    covers too little of it (or whose words' boxes do), or one whose text is not the row's. A display line of three words or fewer must also hold the same words, since a
    letterspaced word is often read as two."""
    if len(mine) != 1:
        return True
    x, _, w, h = row.box
    bx, _, bw, bh = boxes[0]
    out = bx < x - 0.5 * h or bx + bw > x + w + 0.5 * h or bh > 1.6 * h
    if out or likeness(read, text) < 0.6 or _share(row.box, boxes[0]) < 0.5:
        return True
    words = [
        cast("Box", tuple(int(v) for v in wd["box"])) for wd in cast("list[dict[str, Any]]", mine[0].get("words") or [])
    ]
    for g in row.glyphs:
        if g[3] >= LETTER[0] * h and g[2] >= LETTER[1] * h:
            middle = g[0] + g[2] / 2
            if not any(b[0] - 4 <= middle <= b[0] + b[2] + 4 for b in words):
                return True  # a letter of the row that no word's box holds ("AND" boxed as "AN")
    return len(text.split()) <= 3 and len(mine[0].get("words") or []) != len(text.split())
