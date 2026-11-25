"""The quality gate on a page set again in type: whether the rebuilt page may stand in the finished PDF in place of its scan. A page that fails
keeps its scan (with the searchable text under it), so the finished PDF is always complete and never worse than the scans.

Four checks, each with its mark (Jonathan, 2026-11-24, set on 14 of the hardest pages of two books; test them on others before trusting the
numbers, they were chosen knowing which of those pages looked right):

    words    at most LOST of the corrected text's words are missing from the PDF's text. The characters of the corrected text may be right
             while the PDF drops or misplaces lines, so the reading's own error says nothing about this
    overlap  at most OVERLAP of the characters lie on top of another, and none off the page: a line sized far too big, or drawn over another
    ink      the rebuilt page's ink agrees with the scan's on the text to at least INK (F1 within a pixel or two, strata-models' `ink` measure,
             reproduced here so the gate needs no service): a page that is not print (marbled paper, a handwritten note) or is set in the wrong
             place fails it
    symbols  every symbol of the text is in the PDF and drawn (a footnote's † and ‡, brackets): the period fonts lack some, and a missing one is
             a blank or an empty box, which neither the words nor the ink shows. The text layer may still hold it, so the drawing is looked at

    size     no line of a block of text is set more than SIZE times its block's size, and no words that stand on one line differ more than ROW
             in size: a line whose size was fitted wrong (a tall neighbour's descender boxed with it), or a headline's word set small

The words are checked against the page's text and, when there is one, a second reading by another route (a vision-language model on the
picture, pipeline): what both have, and any line either has (`lost_words`).

A check that could not be made (a PDF that will not open) is a failure with the reason, never a pass."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, cast

import cv2
import numpy as np
import pypdfium2 as pdfium  # pyright: ignore[reportMissingTypeStubs]
import pypdfium2.raw as pdfium_c  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray

LOST = 0.01  # share of the corrected text's words
OVERLAP = 0.01  # share of the characters
INK = 0.70
SIZE = 1.25  # set on book 1's 25 rebuilt pages (2026-11-25): flags the four with a line too big by eye and page 7, and no other
ROW = 1.8  # a line's words of three letters or more; small capitals beside capitals differ by about 1.3
# a symbol the two texts may spell differently without being wrong: curly quotes, dashes and hyphens, and the marks dust and broken type make
LOOSE = frozenset("'\"`_.,;:~^|<>\\/-" + "\u00b4\u2018\u2019\u201c\u201d\u2010\u2011\u2013\u2014\u00b7\u2022")

Mask = NDArray[np.bool_]
Gray = NDArray[np.uint8]


@dataclass(frozen=True)
class Verdict:
    """A page's result: the measures, and in words what failed (empty = passed)."""

    words_lost: float
    overlap: float
    off_page: int
    ink: float
    symbols_lost: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.reasons

    def record(self) -> dict[str, Any]:
        """As stored in the page's `ocr["gate"]`: plain JSON."""
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "words_lost": round(self.words_lost, 4),
            "overlap": round(self.overlap, 4),
            "off_page": self.off_page,
            "ink": round(self.ink, 4),
            "symbols_lost": list(self.symbols_lost),
        }


def unbroken(text: str) -> str:
    """Words split at a line end joined: a hyphen there (pdfium gives it as U+FFFE) is the printer's, and the two texts do not split alike."""
    return re.sub(r"[-­￾][ \t]*\r?\n[ \t]*|[­￾]", "", text.replace("\u2019", "'"))


def word_list(text: str) -> list[str]:
    """The text's words in order; a line of one letter or figure is an ornament read as type ("——o——")."""
    lines = [ln for ln in unbroken(text).splitlines() if sum(c.isalnum() for c in ln) > 1]
    return re.findall(r"[^\W_]+", "\n".join(lines).lower())


def words(text: str) -> Counter[str]:
    return Counter(word_list(text))


def symbols(text: str) -> Counter[str]:
    """The text's symbols; not a picture (a pointing hand), which no text face has and the rebuild cuts from the scan (rows.picture_mark)."""
    found = [c for c in text if not c.isspace() and not c.isalnum() and c not in LOOSE and c != "\ufffe"]
    return Counter(c for c in found if unicodedata.category(c) != "So")


def missing(text: str, drawn: str) -> tuple[Counter[str], Counter[str]]:
    """(the words of `text` that `drawn` lacks, each as often as it lacks them; those of them that stand two or more together)."""
    want, have = word_list(text), word_list(drawn)
    lack = Counter(want) - Counter(have)
    met: set[int] = set()
    for a, _, n in SequenceMatcher(None, want, have, autojunk=False).get_matching_blocks():
        met.update(range(a, a + n))
    left, at = Counter(lack), list[int]()
    for i, w in enumerate(want):
        if i not in met and left[w] > 0:
            left[w] -= 1
            at.append(i)
    together = Counter(
        want[i] for k, i in enumerate(at) if i - 1 in at[max(0, k - 1) : k] or i + 1 in at[k + 1 : k + 2]
    )
    return lack, together


def lost_words(text: str, drawn: str, reading: str | None = None) -> tuple[float, Counter[str]]:
    """(the share of the words `drawn` lacks, the words). With a second `reading`, a word counts when both readings have it and the page does
    not, or when it stands in a run either has and the page lacks (a line or more): one reading's lone misreading ("reccms" for rooms) is not
    the page's fault, and no reading can relax what the other saw (a reading that stopped short, a line one of them missed)."""
    lack, together = missing(text, drawn)
    if reading is None:
        return sum(lack.values()) / max(1, sum(words(text).values())), lack
    lack2, together2 = missing(reading, drawn)
    lost = (lack & lack2) | together | together2
    return sum(lost.values()) / max(1, sum(words(text).values()), sum(words(reading).values())), lost


SCALE = 4.0  # pixels a point the symbols are looked at: 288 dpi
EDGE = 0.85  # share of each side of a glyph's outline that is ink on a missing-glyph box


def is_box(ink: Mask) -> bool:
    """Whether a glyph's ink is a frame (the box a font draws for a glyph it lacks): its four outermost rows and columns are inked through."""
    rows, cols = np.nonzero(ink.any(1))[0], np.nonzero(ink.any(0))[0]
    if len(rows) < 6 or len(cols) < 6:
        return False
    g = ink[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
    return all(float(side.mean()) >= EDGE for side in (g[0], g[-1], g[:, 0], g[:, -1]))


def undrawn(doc: Any) -> Counter[str]:
    """The symbols the page's text layer holds but its drawing does not: nothing inked where one stands, or a missing-glyph box."""
    page = doc[0]
    tp = page.get_textpage()
    gray = np.asarray(page.render(scale=SCALE, grayscale=True).to_numpy(), dtype=np.uint8)
    drawn = np.asarray(gray.reshape(gray.shape[:2]) < 128, dtype=np.bool_)
    out: Counter[str] = Counter()
    for i in range(int(tp.count_chars())):
        c = str(tp.get_text_range(i, 1))
        if not symbols(c):
            continue
        left, bottom, right, top = tp.get_charbox(i)
        high = float(page.get_size()[1])
        x0, x1 = int(left * SCALE), int(np.ceil(right * SCALE))
        y0, y1 = int((high - top) * SCALE), int(np.ceil((high - bottom) * SCALE))
        glyph = drawn[max(0, y0) : max(0, y1), max(0, x0) : max(0, x1)]
        if not glyph.any() or is_box(glyph):
            out[c] += 1
    return out


def read_chars(
    pdf: str,
) -> tuple[str, list[tuple[float, float, float, float]], tuple[float, float], Counter[str]]:
    """(text, each visible character's box in points with y up, the page's size, the symbols not drawn)."""
    doc = pdfium.PdfDocument(pdf)
    try:
        page = cast("Any", doc[0])
        tp = page.get_textpage()
        text = str(tp.get_text_range())
        boxes: list[tuple[float, float, float, float]] = []
        for i in range(int(tp.count_chars())):
            if str(tp.get_text_range(i, 1)).strip():
                left, bottom, right, top = tp.get_charbox(i)
                if right > left and top > bottom:
                    boxes.append((left, bottom, right, top))
        size = cast("tuple[float, float]", page.get_size())
        return text, boxes, size, undrawn(doc)
    finally:
        doc.close()


def char_sizes(pdf: str, width: float) -> list[tuple[float, float, float, str]]:
    """Every letter and digit of the page as (x, y, its type size, itself), x and y in the scan's pixels (`width` across), top down."""
    doc = cast("Any", pdfium.PdfDocument(pdf))
    c_api = cast("Any", pdfium_c)
    try:
        page = doc[0]
        wide, high = page.get_size()
        k = width / float(wide)
        tp = page.get_textpage()
        out: list[tuple[float, float, float, str]] = []
        for i in range(int(tp.count_chars())):
            c = str(tp.get_text_range(i, 1))
            if not c.isalnum():
                continue
            left, bottom, right, top = tp.get_charbox(i)
            m = c_api.FS_MATRIX()
            c_api.FPDFText_GetMatrix(tp, i, m)
            size = abs(float(c_api.FPDFText_GetFontSize(tp, i)) * float(m.d))
            if size > 0:
                out.append(((left + right) / 2 * k, (high - (top + bottom) / 2) * k, size, c))
        return out
    finally:
        doc.close()


def wrong_sizes(pdf: str, blocks: list[dict[str, Any]], width: float) -> list[str]:
    """The lines set too big or too small for their place, in words: `SIZE` and `ROW` (module docstring)."""
    chars = char_sizes(pdf, width)
    out: list[str] = []
    for b in blocks:
        if str(b.get("role")) not in ("body", "footnote"):
            continue
        sizes: list[tuple[float, str]] = []
        for x, y, w, h in cast("list[list[float]]", b.get("lines") or []):
            mine = [c for c in chars if x - 8 <= c[0] <= x + w + 8 and y - 0.1 * h <= c[1] <= y + 1.1 * h]
            if len(mine) >= 3:
                sizes.append((float(np.median([c[2] for c in mine])), "".join(c[3] for c in mine)[:20]))
        if len(sizes) >= 3:
            usual = float(np.median([s for s, _ in sizes]))
            out += [f"{t!r} at {s / usual:.1f} times its block" for s, t in sizes if s / usual > SIZE]
    return out


def mixed_rows(pdf: str) -> list[str]:
    """Words of three letters or more that stand on one baseline in sizes over `ROW` apart (a headline whose one word was set small)."""
    doc = cast("Any", pdfium.PdfDocument(pdf))
    c_api = cast("Any", pdfium_c)
    try:
        tp = doc[0].get_textpage()
        words_at: list[tuple[float, float, float, float, str]] = []  # left, right, baseline, size, text
        cur: list[tuple[float, float, float, float, str]] = []

        def end() -> None:
            t = "".join(c[4] for c in cur)
            if len(t) >= 3:
                words_at.append((cur[0][0], cur[-1][1], min(c[2] for c in cur), cur[0][3], t))
            cur.clear()

        for i in range(int(tp.count_chars())):
            c = str(tp.get_text_range(i, 1))
            if not c.isalnum():
                end()
                continue
            left, bottom, right, _ = tp.get_charbox(i)
            m = c_api.FS_MATRIX()
            c_api.FPDFText_GetMatrix(tp, i, m)
            cur.append((left, right, bottom, abs(float(c_api.FPDFText_GetFontSize(tp, i)) * float(m.d)), c))
        end()
    finally:
        doc.close()
    out: list[str] = []
    for i, a in enumerate(words_at):
        for b in words_at[i + 1 :]:
            small, big = sorted((a[3], b[3]))
            if abs(a[2] - b[2]) < 0.25 * small and big / small > ROW and (b[0] >= a[1] or a[0] >= b[1]):
                out.append(f"{a[4]!r} beside {b[4]!r}")
    return out


def overlapping(boxes: list[tuple[float, float, float, float]]) -> int:
    """How many characters lie on a later one, over 30 % of the smaller; a character's next neighbour must cover 60 %, since an italic f leans
    over the letter beside it and a stop stands under it (2026-11-25: 1.4 % of a page of italics). A pair counts once."""
    if len(boxes) < 2:
        return 0
    a = np.asarray(boxes, dtype=np.float64)
    area = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    n = 0
    for i in range(len(a) - 1):
        rest = a[i + 1 :]
        w = np.minimum(a[i, 2], rest[:, 2]) - np.maximum(a[i, 0], rest[:, 0])
        h = np.minimum(a[i, 3], rest[:, 3]) - np.maximum(a[i, 1], rest[:, 1])
        shared = np.maximum(w, 0) * np.maximum(h, 0) / np.maximum(np.minimum(area[i + 1 :], area[i]), 1e-9)
        n += bool(shared[0] > 0.6 or (shared[1:] > 0.3).any())
    return n


def ink_of(gray: Gray, dpi: float) -> Mask:
    """The black of a scanned page: the paper's tone and the gutter's shadow flattened, then Sauvola over about two lines of type, only what is
    also darker than paper, specks (no two neighbours) out. As strata-models' evals/ink.py, so the mark means what it meant there."""
    small = cv2.resize(gray, (max(1, gray.shape[1] // 8), max(1, gray.shape[0] // 8)), interpolation=cv2.INTER_AREA)
    bg = cv2.medianBlur(cv2.dilate(small, np.ones((5, 5), np.uint8)), 13)
    paper = np.asarray(cv2.resize(bg, (gray.shape[1], gray.shape[0])), dtype=np.float32)
    flat = np.minimum(
        gray.astype(np.float32) / np.maximum(paper, np.float32(1.0)) * np.float32(255.0), np.float32(255.0)
    )
    r = max(7, int(dpi / 10))
    k = (2 * r + 1, 2 * r + 1)
    mean = cv2.boxFilter(flat, cv2.CV_32F, k)
    sq = cv2.boxFilter(flat * flat, cv2.CV_32F, k)
    dev = np.sqrt(np.maximum(sq - mean * mean, 0.0))
    ink = (flat <= mean * (1 + 0.2 * (dev / 128.0 - 1))) & (flat < 200)
    near = np.asarray(cv2.boxFilter(ink.astype(np.float32), cv2.CV_32F, (3, 3), normalize=False), dtype=np.float32)
    return np.asarray(ink & (near >= 3), dtype=np.bool_)  # itself and two neighbours


def ink_f1(want: Mask, got: Mask, tol: int, where: Mask) -> float:
    """F1 of `got`'s ink against `want`'s inside `where`, each counted when the other is within `tol` pixels. Both empty is a full agreement."""
    want, got = want & where, got & where
    nw, ng = int(want.sum()), int(got.sum())
    if not nw and not ng:
        return 1.0
    if not nw or not ng:
        return 0.0
    k = np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)
    p = float((got & (cv2.dilate(want.astype(np.uint8), k) > 0)).sum()) / ng
    r = float((want & (cv2.dilate(got.astype(np.uint8), k) > 0)).sum()) / nw
    return 2 * p * r / (p + r) if p + r else 0.0


def scan_width(png: str) -> float:
    scan = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
    if scan is None:
        raise ValueError("the page's picture could not be read")
    return float(scan.shape[1])


def text_ink(pdf: str, png: str, blocks: list[dict[str, Any]], dpi: float) -> float:
    """How well the rebuilt page's ink agrees with the scan's, on the text's own lines (the figures and the paper are not the rebuild's)."""
    scan = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
    if scan is None:
        raise ValueError("the page's picture could not be read")
    gray = np.asarray(scan, dtype=np.uint8)
    h, w = gray.shape
    doc = pdfium.PdfDocument(pdf)
    try:
        page = cast("Any", doc[0])
        drawn = np.asarray(page.render(scale=w / float(page.get_size()[0]), grayscale=True).to_numpy(), dtype=np.uint8)
    finally:
        doc.close()
    drawn = drawn.reshape(drawn.shape[:2])
    got = np.asarray(cv2.resize(drawn, (w, h)) < 128, dtype=np.bool_)
    where = np.zeros((h, w), dtype=np.bool_)
    for b in blocks:
        for x, y, bw, bh in cast("list[list[float]]", b.get("lines") or []):
            where[max(0, int(y - 4)) : max(0, int(y + bh + 4)), max(0, int(x - 4)) : max(0, int(x + bw + 4))] = True
    return ink_f1(ink_of(gray, dpi), got, max(1, round(dpi / 250)), where)


def check_page(
    pdf: str, png: str, text: str, blocks: list[dict[str, Any]], dpi: float, reading: str | None = None
) -> Verdict:
    """The page's verdict. `text` is its corrected (or typed) text, `blocks` its layout's (layout.read_layout), `reading` the second reading:
    the words must be in the page by both, so neither a reading that stopped short nor a line the first one missed can pass it."""
    if not words(text):
        return Verdict(0.0, 0.0, 0, 0.0, (), ("the page has no words to check it by",))
    try:
        drawn, boxes, (wide, high), blank = read_chars(pdf)
        ink = text_ink(pdf, png, blocks, dpi)
        sized = wrong_sizes(pdf, blocks, scan_width(png)) + mixed_rows(pdf)
    except Exception as e:
        return Verdict(1.0, 0.0, 0, 0.0, (), (f"the rebuilt page could not be checked ({type(e).__name__}: {e})",))
    lost, gone = lost_words(text, drawn, reading)
    over = overlapping(boxes) / max(1, len(boxes))
    off = sum(1 for x0, y0, x1, y1 in boxes if x0 < 0 or y0 < 0 or x1 > wide or y1 > high)
    missing = tuple(sorted((symbols(text) - (symbols(drawn) - blank)).elements()))
    reasons: list[str] = []
    if lost > LOST:
        reasons.append(f"{lost:.1%} of the words are missing: " + " ".join(sorted(gone.elements())[:8]))
    if over > OVERLAP:
        reasons.append(f"{over:.1%} of the characters lie over others")
    if off:
        reasons.append(f"{off} characters are off the page")
    if ink < INK:
        reasons.append(f"its ink agrees with the scan's only {ink:.0%}")
    if missing:
        reasons.append("symbols are missing: " + " ".join(missing[:8]))
    if sized:
        reasons.append("type of the wrong size: " + "; ".join(sized[:3]))
    return Verdict(lost, over, off, ink, missing, tuple(reasons))
