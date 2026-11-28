"""What strata-models makes of a page beyond its letters: its layout, and the page set again in matching type. The models and settings are the
winners of strata-models' evals (2026-11-15 to 2026-11-24), measured on whole pages of the two books this app was built for:

    layout   `page-layout`: Tesseract's lines regrouped into blocks with roles by Claude Opus (opus-fix-v2): blocks found 96.5 % (block_f1)
             against Tesseract's own 64 %, about 3 cents a page. `read_layout`
    rebuild  `page-rebuild`, candidate full-opus: that layout, each line's text put right by Claude Haiku (page-text-fix-v1), the type fitted
             (role font-match: the period face, size and style of every word, with Sonnet's shortlist), one size a block, figures and rules
             cut from the scan: ink agreement with the scan 76 % against 37 % for Tesseract's text in Times, about 5 cents and 2 minutes of
             CPU a page. `full-every-face` (every face tried, not the shortlist) agreed 78 %, under the 3 points the eval asks for a change
             and at twice the time, so the shortlist stays. `rebuild_page`

Every call goes through the strata-models service by role; the models are named because the evals measured these ones."""

import itertools
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any, cast

from strata_python.clients import models as sm

from stratascan.align import align, letters

APP = "strata-scan"
LAYOUT_PRESET = "page-layout-fix-v2"
TEXT_PRESET = "page-text-fix-v1"
READ_PRESET = "ocr-read-v2"
TEXT_MODEL = "claude-haiku-5-5-api"
# `pagebuild` only draws: the role's default model would ask Opus for a layout of its own
DRAW = "pagebuild"
FULL: dict[str, Any] = {"snap": 0.1, "styles": ["roman", "italic"], "crop": True, "rules": True}
NUMBERED = re.compile(r"^(\d+) b-?\d+ \[[^\]]*\] (.*)$")

# (role, params, model) -> the job's result: sm.run, or a stand-in in tests
RunFn = Callable[[str, dict[str, Any], "str | None"], Mapping[str, Any]]


class LayoutError(RuntimeError):
    """A failure to show the person, in words."""


class CallError(LayoutError):
    """A model was not reached, or its job failed: no answer at all, unlike an answer that was no layout. A page whose layout call failed is
    asked again before it is set, never set without one (Jonathan, 2026-11-27)."""


def models_run(role: str, params: dict[str, Any], model: str | None) -> Mapping[str, Any]:
    try:
        return sm.run(role, params, app=APP, model=model)
    except sm.Unavailable as e:
        raise CallError(f"strata-models is not running ({e})") from e
    except sm.JobFailed as e:
        raise CallError(f"strata-models could not do it ({role}): {e}") from e


def plain(ocr: Mapping[str, Any]) -> dict[str, Any]:
    """The OCR answer without what this app added to it."""
    return {k: ocr[k] for k in ("width", "height", "text", "lines") if k in ocr}


def answer_json(r: Mapping[str, Any]) -> dict[str, Any]:
    """A preset's JSON answer: `json` as the service parsed it, else its text parsed here (code fences allowed)."""
    v = r.get("json")
    if not isinstance(v, dict):
        t = str(r.get("text") or "")
        a, b = t.find("{"), t.rfind("}")
        try:
            v = json.loads(t[a : b + 1])
        except ValueError:
            raise LayoutError("the model's answer was not JSON") from None
        if not isinstance(v, dict):
            raise LayoutError("the model's answer was not JSON")
    return cast("dict[str, Any]", v)


def numbered(ocr: Mapping[str, Any], run: RunFn = models_run) -> str:
    """The OCR's lines as the presets are shown them, one a line: number, block, box in thousandths, text."""
    return str(run("page-build", {"ocr": plain(ocr), "list_lines": True}, DRAW).get("text") or "")


def layout_params(png: str, context: str) -> dict[str, Any]:
    """The layout call's params for a page whose numbered lines are `context` (`read_layout`; planned ahead by the read stage)."""
    return {"preset": LAYOUT_PRESET, "context": context, "image": png, "max_tokens": 8192}


def text_params(png: str, context: str) -> dict[str, Any]:
    """The call putting each line's text right, for a page whose numbered lines are `context` (`rebuild_page`; planned ahead)."""
    return {"preset": TEXT_PRESET, "context": context, "image": png, "max_tokens": 8192}


PROPOSE_MODEL = (
    "claude-sonnet-5-5-api"  # the font-match proposer strata-models' font-match eval chose (models.toml `propose`)
)
PROPOSE_PRESET = "font-propose-v1"
PROPOSE_PROMPT = "Identify the typeface of the printed text in this picture."  # strata-models fontfit.PROPOSE_PROMPT


def propose_params(png: str) -> dict[str, Any]:
    """The font-match proposer's call for a whole page: its answer, any text naming faces, is a shortlist font-match takes as `candidates`."""
    return {"system_preset": PROPOSE_PRESET, "prompt": PROPOSE_PROMPT, "image": png, "max_tokens": 1500}


def read_params(png: str) -> dict[str, Any]:
    """The call reading a page from its picture alone (`read_again`; planned ahead)."""
    return {"image": png, "prompt": "Transcribe this page.", "system_preset": READ_PRESET, "max_tokens": 4096}


def settled(ocr: Mapping[str, Any], was: Mapping[str, Any] | None, run: RunFn = models_run) -> Mapping[str, Any]:
    """The OCR answer a stored layout's line numbers refer to: `ocr` (tidied), unless its lines are split otherwise than `was`, the answer
    the layout was read from; then `was`, with the layout."""
    if was is not None and (numbered(ocr, run).count("\n") != numbered(was, run).count("\n")):
        return dict(was, layout=ocr.get("layout") or {})
    return ocr


PLAIN = "plain"  # a layout's `model` when it was worked out from the page's own lines (`plain_groups`), no model asked
PLAIN_LINES = 12  # a page of fewer lines is a title, a notice or a scrap: the layout model reads it
PLAIN_SPREAD = 1.6  # its lines' heights (90th percentile over 10th) at most this far apart: one size of type, with its smaller verse
GAP = 1.8  # times the usual distance from one line to the next: a gap between blocks


def numbered_lines(context: str) -> list[tuple[int, list[float], str]]:
    """(number, box in thousandths [x0, y0, x1, y1], text) of each line of `numbered`'s list."""
    out: list[tuple[int, list[float], str]] = []
    for m in re.finditer(r"^(\d+) b-?\d+ \[([\d.,-]+)\] ?(.*)$", context, re.M):
        box = [float(v) for v in m[2].split(",")]
        if len(box) == 4:
            out.append((int(m[1]), box, m[3]))
    return out


def plain_groups(context: str) -> dict[str, Any] | None:
    """A plain page's layout from its own lines, or None when the page is not plain. Plain: a page of running text in one size of type, its
    lines no further apart in height than PLAIN_SPREAD, and enough of them. Its layout is the running head and page number at the top (a
    lone figure at the foot is the page number too), centred short lines standing alone are headings, and the rest is body text in blocks
    parted where a gap falls. Few blocks rather than many: a block's sizes are snapped to one (page-build). This is what the layout model answered for the 1874 book's pages of dialogue
    (2026-11-26), and asking it was two thirds of the cost of setting a book in type."""
    rows = sorted(numbered_lines(context), key=lambda t: t[1][1])
    texty = [r for r in rows if sum(c.isalpha() for c in r[2]) >= 3]
    if len(texty) < PLAIN_LINES:
        return None
    heights = sorted(r[1][3] - r[1][1] for r in texty)
    low, high = heights[len(heights) // 10], heights[(9 * len(heights)) // 10]
    if low <= 0 or high > PLAIN_SPREAD * low:
        return None
    usual = heights[len(heights) // 2]
    # two columns: lines side by side on one row. Sorted top down they would interleave, so the layout model reads such a page (review)
    beside = sum(
        1
        for i, a in enumerate(texty)
        for b in texty[i + 1 :]
        if min(a[1][3], b[1][3]) - max(a[1][1], b[1][1]) > 0.5 * usual and (a[1][2] <= b[1][0] or b[1][2] <= a[1][0])
    )
    if beside >= 3:
        return None
    left = min(r[1][0] for r in texty)
    right = max(r[1][2] for r in texty)
    middle = (left + right) / 2
    roles: dict[int, str] = {}
    # no streak read as a line far taller than the type (left out, as the layout model leaves it), and no mark of the frame above the type
    rows = [
        r
        for r in rows
        if r[1][3] - r[1][1] <= 2.5 * usual and (r[1][2] - r[1][0] > r[1][3] - r[1][1] or r[2].strip().isdigit())
    ]  # nor a narrow one, but for a page number
    rows = [r for r in rows if r[1][1] >= texty[0][1][1] - usual or r[2].strip().isdigit()]
    if not rows:
        return None
    top = rows[0][1][1]
    head = [r for r in rows if r[1][1] <= top + usual]  # the first line, in its pieces
    for n, _box, text in head:
        letters = [c for c in text if c.isalpha()]
        if not letters and any(c.isdigit() for c in text):
            roles[n] = "folio"
        elif letters and sum(c.isupper() for c in letters) / len(letters) > 0.7 and len(text.split()) <= 8:
            roles[n] = "running-head"
    if "running-head" in roles.values() and "folio" not in roles.values():
        return None  # a line of capitals with no page number beside it may be a chapter's title: the layout model tells them apart (review)
    if "running-head" not in roles.values():
        roles = {}  # what stood at the top is the text's, set as the text's (the 1874 book's PREFACE)
    if rows[-1][2].strip().isdigit():
        roles[rows[-1][0]] = "folio"
    blocks: list[dict[str, Any]] = [{"lines": [n], "role": role} for n, role in roles.items()]
    body = [r for r in rows if r[0] not in roles]
    pitch = sorted(b[1][1] - a[1][1] for a, b in itertools.pairwise(body) if b[1][1] > a[1][1]) or [usual]
    step = pitch[len(pitch) // 2]
    current: list[int] = []
    last: tuple[int, list[float], str] | None = None
    for i, (n, box, text) in enumerate(body):
        width = box[2] - box[0]
        centred = abs((box[0] + box[2]) / 2 - middle) < 0.05 * (right - left) and width < 0.6 * (right - left)
        alone = (last is None or box[1] - last[1][1] > GAP * step) and (
            i + 1 == len(body) or body[i + 1][1][1] - box[1] > GAP * step
        )
        if centred and alone and len(text.split()) <= 6:
            if current:
                blocks.append({"lines": current, "role": "body"})
                current = []
            blocks.append({"lines": [n], "role": "heading"})
            last = (n, box, text)
            continue
        parted = last is not None and box[1] - last[1][1] > GAP * step
        if current and parted:
            blocks.append({"lines": current, "role": "body"})
            current = []
        current.append(n)
        last = (n, box, text)
    if current:
        blocks.append({"lines": current, "role": "body"})
    return {"blocks": blocks, "figures": []}


def read_layout(
    png: str,
    ocr: Mapping[str, Any],
    model: str,
    dpi: int,
    run: RunFn = models_run,
    groups: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A page's layout as {model, groups, blocks: [{role, lines: [box, ...]}]}: the model's groups of numbered lines (what `rebuild_page`
    draws again) and, for the export, each block's role with its lines' boxes in page pixels, in reading order. With `groups` (a plain page's,
    `plain_groups`) no model is asked."""
    context = numbered(ocr, run)
    if not context:
        raise LayoutError("the page has no lines to lay out")
    if groups is None:
        groups = answer_json(run("vision-language", layout_params(png, context), model))
    else:
        model = PLAIN
    if not groups.get("blocks"):
        raise LayoutError("the layout model found no blocks")
    with tempfile.TemporaryDirectory() as tmp:
        drawn = run(
            "page-build",
            {
                "ocr": plain(ocr),
                "groups": groups,
                "image": png,
                "dpi": dpi,  # the page pictures carry none
                "png": False,
                "out": os.path.join(tmp, "layout.pdf"),
            },
            DRAW,
        )
    page = cast("Mapping[str, Any]", drawn.get("page") or {})
    blocks: list[dict[str, Any]] = []
    for b in cast("list[dict[str, Any]]", page.get("blocks") or []):
        lines = [list(ln["box"]) for ln in cast("list[dict[str, list[float]]]", b.get("lines") or [])]
        blocks.append({"role": str(b.get("role") or "body"), "lines": lines})
    if not any(b["lines"] for b in blocks):
        raise LayoutError("the layout model's blocks hold none of the lines")
    return {"model": model, "groups": groups, "blocks": blocks}


COLOUR = 60  # saturation (0-255), once the paper is made white, above which a pixel is coloured ink
COLOURED = 0.05  # share of a picture's printed pixels that are coloured for it to be kept in colour; less is grey (Jonathan, 2026-11-27)
JPEG = 85  # quality of the pictures a rebuilt page carries: lossy, as a scan's picture already is (lossless made a plate 20 MB)


def whitened(rgb: Any) -> Any:
    """`rgb` (float, h x w x 3) with each channel over the paper's own tone (its 90th percentile): yellowed paper white, its ink as printed."""
    import numpy as np

    npa: Any = np  # numpy's percentile and clip overloads are partially unknown to pyright
    paper = np.maximum(npa.percentile(rgb.reshape(-1, 3), 90, axis=0), 1.0)
    return npa.clip(rgb * (255.0 / paper), 0, 255)


def has_colour(rgb: Any, whiten: bool = True) -> bool:
    """Whether a picture (float RGB) shows real colour once its paper is white: a hand-coloured plate, a red stamp, a cloth cover; not an
    engraving on browned paper, nor foxing (a few spots)."""
    import numpy as np
    from PIL import Image

    # a cut picture is looked at with its paper made white (a browned leaf is no colour); a cover as it is, since whitening a red cloth
    # takes its colour for the paper's and leaves only its black lettering (review)
    npa: Any = np
    flat = (whitened(rgb) if whiten else npa.clip(rgb, 0, 255)).astype(np.uint8)
    hsv = np.asarray(Image.fromarray(flat, "RGB").convert("HSV"), dtype=np.uint8)
    coloured = (hsv[..., 1] > COLOUR) & (hsv[..., 2] > 50)
    # a share of what is printed, not of the picture: a red bookplate among handwriting on a white leaf is a small part of its picture
    # but much of its ink (the 1828 book's endpaper came out grey, 2026-11-28)
    printed = (flat.min(axis=2) < 235) | coloured
    return float(coloured.sum()) > COLOURED * max(float(printed.sum()), 0.05 * coloured.size)


def save_picture(img: Any, out: str, as_is: bool = False) -> str:
    """`img` (a PIL image) written to `out` as a JPEG, in grey unless it shows colour (`has_colour`; `as_is`: a cover or a pattern, looked
    at without whitening); its path."""
    import numpy as np

    rgb = img.convert("RGB")
    keep = rgb if has_colour(np.asarray(rgb, dtype=np.float32), whiten=not as_is) else rgb.convert("L")
    keep.save(out, "JPEG", quality=JPEG, optimize=True)
    return out


def cut_picture(png: str, box: tuple[int, int, int, int], out: str) -> str:
    """The picture at `box` (page pixels) cut from the scan with its paper made white, as a JPEG at `out` (`save_picture`): grey for an
    engraving, in colour for a coloured print. The paper is the whole page's, not the picture's: a densely hatched engraving is mostly ink,
    and whitened by itself its paper stayed a grey box. Its path."""
    import numpy as np
    from PIL import Image

    npa: Any = np
    x, y, w, h = box
    with Image.open(png) as im:
        page = np.asarray(im.convert("RGB"), dtype=np.float32)
    paper = np.maximum(npa.percentile(page[::4, ::4].reshape(-1, 3), 90, axis=0), 1.0)
    part = npa.clip(page[y : y + h, x : x + w] * (255.0 / paper), 0, 255)
    return save_picture(Image.fromarray(part.astype(np.uint8), "RGB"), out)


def cut_as_is(png: str, box: tuple[int, int, int, int], out: str) -> str:
    """The scan at `box` (page pixels), its paper left as it is (a cover, a pattern), as a JPEG at `out` (`save_picture`); its path."""
    from PIL import Image

    x, y, w, h = box
    with Image.open(png) as im:
        return save_picture(im.convert("RGB").crop((x, y, x + w, y + h)), out, as_is=True)


def picture_box(
    png: str, box: tuple[int, int, int, int], text: Sequence[tuple[int, int, int, int]]
) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the picture a layout boxed at `box` (page pixels), from the ink itself: the ink near the box that is not the page's
    text (`text`: its lines' boxes), joined into the shapes it makes, those that reach into the box together. A layout model's box is a
    guess: the third book's page 15 lost the top of its engraving, and its box ran on over the caption and the text below, drawn twice."""
    import cv2
    import numpy as np

    npa: Any = np
    cv: Any = cv2
    g = cv.imread(png, cv.IMREAD_GRAYSCALE)
    if g is None:
        return box
    high, wide = g.shape
    g = npa.clip(g.astype(np.float32) * (255.0 / max(float(npa.percentile(g[::4, ::4], 90)), 1.0)), 0, 255)
    ink = (g < 0.7 * 255).astype(np.uint8)
    pad = max(2, round(0.004 * high))
    for x, y, w, h in text:
        ink[max(0, y - pad) : y + h + pad, max(0, x - pad) : x + w + pad] = 0
    k = (
        max(3, round(0.012 * min(wide, high))) | 1
    )  # an engraving's strokes joined into one shape, not its lines to the text's
    ink = cv.morphologyEx(ink, cv.MORPH_CLOSE, np.ones((k, k), np.uint8))
    x, y, w, h = box
    mx, my = round(0.15 * wide), round(0.15 * high)  # how far the picture may reach past the box it was given
    x0, y0, x1, y1 = max(0, x - mx), max(0, y - my), min(wide, x + w + mx), min(high, y + h + my)
    n, _, st, _ = cv.connectedComponentsWithStats(ink[y0:y1, x0:x1], connectivity=8)
    keep: list[tuple[int, int, int, int]] = []
    for i in range(1, n):
        cx, cy, cw, ch, area = (int(v) for v in st[i])
        if area < 0.001 * wide * high:
            continue  # a speck, a stray letter
        ax, ay = x0 + cx, y0 + cy
        if ax < x + w and ax + cw > x and ay < y + h and ay + ch > y:  # it reaches into the box
            keep.append((ax, ay, ax + cw, ay + ch))
    if not keep:
        return box
    bx0, by0 = min(b[0] for b in keep), min(b[1] for b in keep)
    bx1, by1 = max(b[2] for b in keep), max(b[3] for b in keep)
    if (bx1 - bx0) * (by1 - by0) < 0.25 * w * h:
        return box  # ink found is a sliver of the box: a pale picture, kept as boxed
    return bx0, by0, bx1 - bx0, by1 - by0


def merged_figures(laid: Sequence[Mapping[str, Any]], read: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The layout's pictures (boxes in thousandths) that are boxes of the page, and each picture the read found (`figures.py`, or a person
    drew) that none of them covers: a layout model can name a picture in the wrong units (the third book's page 16: y to 1630 of 1000) or
    miss it, and the page was set without its engraving."""

    def sound(b: Sequence[Any]) -> bool:
        return (
            len(b) == 4
            and all(0 <= float(v) <= 1000 for v in b)
            and float(b[2]) > float(b[0])
            and float(b[3]) > float(b[1])
        )

    kept = [dict(f) for f in laid if f.get("kind") == "rule" or sound(cast("list[Any]", f.get("box") or []))]
    boxes = [cast("list[float]", f["box"]) for f in kept if f.get("kind") != "rule"]
    for f in read:
        b = cast("list[float]", f.get("box") or [])
        if not sound(b):
            continue
        area = (b[2] - b[0]) * (b[3] - b[1])
        covered = sum(
            max(0.0, min(b[2], o[2]) - max(b[0], o[0])) * max(0.0, min(b[3], o[3]) - max(b[1], o[1])) for o in boxes
        )
        if covered < 0.5 * area:
            kept.append(dict(f))
    return kept


def with_figure_pictures(groups: Mapping[str, Any], png: str, folder: str, context: str = "") -> dict[str, Any]:
    """The layout's groups with each picture (not a rule) given its own cut (`cut_picture`, a JPEG in `folder`), which page-build draws as
    given: its own crops were lossless grey, so a hand-coloured plate lost its colour and a page with a plate weighed megabytes. Its box is
    found again from the ink (`picture_box`), clear of the page's text: the lines of the layout's blocks, from `context` (`numbered`)."""
    from PIL import Image

    figs = cast("list[dict[str, Any]]", groups.get("figures") or [])
    if not figs:
        return dict(groups)
    with Image.open(png) as im:
        wide, high = im.size
    os.makedirs(folder, exist_ok=True)
    blocks = cast("list[dict[str, list[Any]]]", groups.get("blocks") or [])
    set_lines = {int(n) for b in blocks for n in b.get("lines") or []}
    text = [
        (
            round(b[0] * wide / 1000),
            round(b[1] * high / 1000),
            round((b[2] - b[0]) * wide / 1000),
            round((b[3] - b[1]) * high / 1000),
        )
        for n, b, _t in numbered_lines(context)
        if n in set_lines
    ]
    out: list[dict[str, Any]] = []
    found_px: list[tuple[int, int, int, int]] = []
    for k, f in enumerate(figs):
        box = cast("list[float]", f.get("box") or [])
        if (
            f.get("kind") == "rule" or f.get("image") or len(box) != 4
        ):  # a layout names pictures figure, engraving, photo...
            out.append(f)
            continue
        x0, y0 = max(0, round(box[0] * wide / 1000)), max(0, round(box[1] * high / 1000))
        x1, y1 = min(wide, round(box[2] * wide / 1000)), min(high, round(box[3] * high / 1000))
        if x1 - x0 < 2 or y1 - y0 < 2:
            out.append(f)
            continue
        px, py, pw, ph = picture_box(png, (x0, y0, x1 - x0, y1 - y0), text)
        if any(
            max(0, min(px + pw, a + c) - max(px, a)) * max(0, min(py + ph, b + d) - max(py, b))
            > 0.6 * min(pw * ph, c * d)
            for a, b, c, d in found_px
        ):
            continue  # the same picture found again (the layout's box and the read's, both put right): drawn once
        found_px.append((px, py, pw, ph))
        name = f"{os.path.splitext(os.path.basename(png))[0]}.fig{k}.jpg"
        found = [1000 * px / wide, 1000 * py / high, 1000 * (px + pw) / wide, 1000 * (py + ph) / high]
        out.append(dict(f, box=found, image=cut_picture(png, (px, py, pw, ph), os.path.join(folder, name))))
    return dict(groups, figures=out)


def picture_page(
    png: str,
    boxes: list[tuple[int, int, int, int]],
    out: str,
    dpi: int,
    run: RunFn = models_run,
    crops: str | None = None,
    images: list[str] | None = None,
    rules: bool = True,
    whole: bool = False,
) -> None:
    """A page with no text set again: its pictures (page pixels [x, y, w, h]) cut from the scan onto clean paper, in colour when printed in
            colour (`cut_picture`, into the folder `crops`), its rules drawn; no pictures, a blank page of its size (Jonathan, 2026-11-26: blanks as
            true blanks, only pictures and patterns kept from the scan). `images`: the pictures already made (marks lifted off the paper, in
        marks.py), one for each box, in place of cutting them; `rules`: draw the page's rules (none round handwriting). `whole`: the scan kept as
    it is (a cover, a pattern, the book photographed), cut but not made paper-white: a cloth cover is no engraving on paper."""
    from PIL import Image

    with Image.open(png) as im:
        wide, high = im.size
    folder = crops or os.path.dirname(out)
    figures = [
        {
            "box": [1000 * x / wide, 1000 * y / high, 1000 * (x + w) / wide, 1000 * (y + h) / high],
            "kind": "figure",
            "image": images[k]
            if images is not None
            else (cut_as_is if whole else cut_picture)(
                png, (x, y, w, h), os.path.join(folder, f"{os.path.basename(out)}.{k}.jpg")
            ),
        }
        for k, (x, y, w, h) in enumerate(boxes)
    ]
    params: dict[str, Any] = {
        "ocr": {"width": wide, "height": high, "lines": []},
        "groups": {"blocks": [], "figures": figures},
        "image": png,
        "dpi": dpi,
        "out": out,
        "png": False,
        "rules": rules and bool(boxes),
    }
    run("page-build", params, DRAW)


def rebuild_page(
    png: str,
    ocr: Mapping[str, Any],
    out: str,
    dpi: int,
    typed: str | None = None,
    run: RunFn = models_run,
    corrected: str | None = None,
    was: Mapping[str, Any] | None = None,
    faces: list[str] | None = None,
) -> list[str]:
    """The page set again as a PDF with real text at `out`, from its stored layout (`ocr["layout"]["groups"]`). `typed` is a person's text:
    it goes in as it stands, so a page whose typed lines are not the printed ones cannot be set line for line. `corrected` is the page's
    corrected text, whose words put misread ones right (`with_corrected`). `faces` is the book's font shortlist, so none is asked for; the answer is the
    shortlist the fit used (`proposed`). `was` is the OCR answer the layout was read from, when `ocr` is that answer tidied."""
    layout = cast("dict[str, Any]", ocr.get("layout") or {})
    groups = layout.get("groups")
    if not groups:
        raise LayoutError(str(layout.get("error") or "the page's layout has not been read: read the page again"))
    ocr = settled(ocr, was, run)  # its lines may be split otherwise, so the layout's numbers would be other lines'
    base = plain(ocr)
    context = numbered(ocr, run)
    if typed is None:
        try:
            fixed = answer_json(run("vision-language", text_params(png, context), TEXT_MODEL))
        except LayoutError:
            fixed = {}  # no line fix: the corrected text's words put right what they can, and the page is set all the same
        texts = with_corrected(fixed, corrected or "", context)
    else:
        texts = typed_texts(typed, context)
    asked: dict[str, Any] = {"mode": "fit", "lines": base.get("lines") or [], "image": png, "dpi": dpi}
    if faces:
        asked.update(candidates=faces, propose=False)  # the book's shortlist: no model asked for one
    fit = run("font-match", asked, None)
    crops = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(out))), "crops"
    )  # beside the book's rebuilt/ (files.py)
    run(
        "page-build",
        {
            "ocr": base,
            "groups": with_figure_pictures(groups, png, crops, context),
            "texts": texts,
            "font_fit": dict(fit),
            "image": png,
            "dpi": dpi,
            "out": out,
            "png": False,
            **FULL,
        },
        DRAW,
    )
    return [str(f) for f in cast("list[Any]", fit.get("proposed") or [])]


def read_again(png: str, run: RunFn = models_run) -> str:
    """The page's text read by the text model from the picture alone, with no OCR to lean on: what the gate checks a rebuilt page's words
    against. eval ocr-lines (2026-11-24, 20 hard pages): Haiku finds 99.8 % of the printed lines, 0.3 % of characters wrong, $0.0008 a page."""
    return str(run("vision-language", read_params(png), TEXT_MODEL).get("text") or "")


def with_corrected(texts: Mapping[str, Any], corrected: str, context: str) -> dict[str, Any]:
    """page-text-fix's answer with its misread words put right from the page's corrected text. The correction reads a cleaned page (ocr-hard,
    2026-11-24) and gets small capitals right that the line fix leaves misread ("PorrLy" for POLLY on the 1874 book). Only word for word, a word by the
    like word that stands for it (align.py), so the lines and their breaks stay the print's (a correction may join a paragraph's lines,
    which set on one of them ran off the page), and words the correction lacks (a running head) stay as they are."""
    nums = [(int(m[1]), m[2]) for m in (NUMBERED.match(x) for x in context.splitlines()) if m]
    fixed = {int(x["n"]): str(x["text"]) for x in cast("list[dict[str, Any]]", texts.get("lines") or [])}
    # a line the fix emptied is tried with the OCR's words: junk has no like in the text and stays empty, a page number does ("29" for 22)
    emptied = {n: t.split() for n, t in nums if not fixed.get(n, t).strip()}
    lines = {n: emptied.get(n) or fixed.get(n, t).split() for n, t in nums}
    where = [(n, k) for n, ws in lines.items() for k in range(len(ws))]
    old = [lines[n][k] for n, k in where]
    new = corrected.split()
    m = SequenceMatcher(None, [letters(w) for w in old], [letters(w) for w in new], autojunk=False)
    changed: set[int] = set()
    found: Counter[int] = Counter()  # words of each line that the text has
    for op, i1, i2, j1, j2 in m.get_opcodes():
        if op == "equal":
            found.update(where[i][0] for i in range(i1, i2))
            for i, j in zip(range(i1, i2), range(j1, j2), strict=True):
                if same_word(old[i], new[j]):  # the same word, but for a mark the line fix missed
                    n, at = where[i]
                    lines[n][at] = new[j]
                    changed.add(n)
        if op != "replace":
            continue
        for b, k in enumerate(align(new[j1:j2], old[i1:i2])):  # alike words only, in order
            if k is None or not same_word(old[i1 + k], new[j1 + b]):
                continue
            n, at = where[i1 + k]
            split = old[i1 + k].endswith("-") or (i1 + k > 0 and old[i1 + k - 1].endswith("-"))
            if not split:  # half of a word the print broke at a line end: the correction has it whole
                lines[n][at] = new[j1 + b]
                changed.add(n)
                found[n] += 1
    for n, ws in emptied.items():
        if ws and found[n] >= len(ws):
            changed.add(n)
        else:
            lines[n] = []
            changed.discard(n)
    read = {n: t.split() for n, t in nums}
    for n, ws in lines.items():
        # only in a line of capitals and small letters: a line of display capitals stays in capitals ("TOYS AND FANCY GOODS")
        if len(ws) == len(read[n]) and sum(any(c.islower() for c in w) for w in ws) > len(ws) / 2:
            for k, (was, now) in enumerate(zip(read[n], ws, strict=True)):
                if small_capitals(was, now) != now:
                    ws[k] = small_capitals(was, now)
                    changed.add(n)
    for n in changed:
        fixed[n] = " ".join(lines[n])
    return {**texts, "lines": [{"n": n, "text": t} for n, t in sorted(fixed.items())]}


def small_capitals(was: str, now: str) -> str:
    """A name set in small capitals, as the OCR saw it (`was`, in capitals and small letters: "Puxca.—What") and as the correction gives it in
    capitals ("PUNCH.—What"): capital and small letters, as elsewhere in the book, so it is not set half as wide again as its print."""
    head = re.match(r"[^A-Za-z]*[A-Za-z]+", was)
    if not head or not any(c.islower() for c in head[0]) or not any(c.isupper() for c in head[0]):
        return now
    return re.sub(r"[A-Z]{3,}", lambda m: m[0].capitalize(), now, count=1)


def with_pictures(laid: dict[str, Any], boxes: list[list[int]], shape: tuple[int, ...]) -> dict[str, Any]:
    """The layout with pictures in its figures (page-build cuts them from the scan; corners in thousandths of the page)."""
    high, wide = shape[0], shape[1]
    more = [
        {
            "kind": "ornament",
            "box": [1000 * x / wide, 1000 * y / high, 1000 * (x + w) / wide, 1000 * (y + h) / high],
        }
        for x, y, w, h in boxes
    ]
    groups = cast("dict[str, Any]", laid["groups"])
    return dict(laid, groups=dict(groups, figures=[*cast("list[Any]", groups.get("figures") or []), *more]))


def with_left_out(laid: dict[str, Any], context: str, ocr: Mapping[str, Any]) -> dict[str, Any]:
    """The layout with the lines put on their rows (rows.repair: their block is 1000 or more) that its model put in no block: they are the page's
    text, not junk it may leave out. Their boxes join `blocks` too, which the gate looks at the ink of."""
    groups = cast("dict[str, Any]", laid["groups"])
    blocks = list(cast("list[dict[str, Any]]", groups.get("blocks") or []))
    taken = {int(n) for b in blocks for n in cast("list[Any]", b.get("lines") or [])}
    ours = [int(m[1]) for m in re.finditer(r"^(\d+) b(\d{4,}) ", context, re.M)]
    new = [n for n in ours if n not in taken]
    blocks += [{"lines": [n], "role": "body"} for n in new]
    seen = [*cast("list[dict[str, Any]]", laid.get("blocks") or [])]
    covered = [[float(v) for v in box] for b in seen for box in cast("list[list[float]]", b["lines"])]
    for ln in cast("list[dict[str, Any]]", ocr.get("lines") or []):
        box = [float(v) for v in ln["box"]]
        if int(ln.get("block") or 0) >= 1000 and not any(
            abs(box[0] - c[0]) < 9 and abs(box[1] - c[1]) < 9 for c in covered
        ):
            seen.append({"role": "body", "lines": [box]})
    return dict(laid, groups=dict(groups, blocks=blocks), blocks=seen)


NOTES = frozenset("*\u2020\u2021\u00a7\u00b6\u2016")  # reference marks: a footnote's, which a reading often misses
MARKS = NOTES | frozenset("[]")  # and a bracket closing a stage direction, which Tesseract leaves out at a line end


def same_word(old: str, new: str) -> bool:
    """Whether `new` may stand for `old`: they differ, and neither holds much more than the other (two words the OCR ran together, half a word)."""
    a, b = letters(old), letters(new)
    if (
        not a and not b
    ):  # a footnote's mark misread as another sign ("+" for "\u2020", 2026-11-26): the corrected text's
        return old != new and bool(set(new) & NOTES) and not set(old) & NOTES
    if (
        a and a == b
    ):  # the same word with a mark the reading missed ("Faustus," for "Faustus,\u2020", "again." for "again.]")
        return bool(set(new) & MARKS - set(old))
    return bool(a and b) and a != b and 0.75 * len(a) <= len(b) <= 1.4 * len(a)


def typed_texts(typed: str, context: str) -> dict[str, Any]:
    """A person's text as page-text-fix's answer: every numbered line given the typed line it is, and an empty text (not drawn) when the
    person left it out."""
    nums = [(int(m[1]), m[2]) for m in (NUMBERED.match(x) for x in context.splitlines()) if m]
    lines = [x for x in typed.splitlines() if x.strip()]
    where = align(lines, [t for _, t in nums])
    if None in where:
        lost = lines[where.index(None)]
        raise LayoutError(f"the typed text does not follow the page's printed lines ({lost[:40]!r})")
    got = {j: lines[i] for i, j in enumerate(where)}
    return {"lines": [{"n": n, "text": got.get(k, "")} for k, (n, _) in enumerate(nums)]}
