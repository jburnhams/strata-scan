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
from collections.abc import Callable, Mapping
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


def models_run(role: str, params: dict[str, Any], model: str | None) -> Mapping[str, Any]:
    try:
        return sm.run(role, params, app=APP, model=model)
    except sm.Unavailable as e:
        raise LayoutError(f"strata-models is not running ({e})") from e
    except sm.JobFailed as e:
        raise LayoutError(f"strata-models could not do it ({role}): {e}") from e


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
    lone = "folio" not in roles.values() and len(head) == 1 and len(head[0][2].split()) < 2
    if "running-head" not in roles.values() or lone:
        roles = {}  # one word of capitals and no page number is the page's heading, set as the text's (the 1874 book's PREFACE)
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
        texts = with_corrected(
            answer_json(run("vision-language", text_params(png, context), TEXT_MODEL)), corrected or "", context
        )
    else:
        texts = typed_texts(typed, context)
    asked: dict[str, Any] = {"mode": "fit", "lines": base.get("lines") or [], "image": png, "dpi": dpi}
    if faces:
        asked.update(candidates=faces, propose=False)  # the book's shortlist: no model asked for one
    fit = run("font-match", asked, None)
    run(
        "page-build",
        {
            "ocr": base,
            "groups": groups,
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


def same_word(old: str, new: str) -> bool:
    """Whether `new` may stand for `old`: they differ, and neither holds much more than the other (two words the OCR ran together, half a word)."""
    a, b = letters(old), letters(new)
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
