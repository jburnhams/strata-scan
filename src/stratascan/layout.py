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

import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from typing import Any, cast

from strata_python.clients import models as sm

from stratascan.align import align

APP = "strata-scan"
LAYOUT_PRESET = "page-layout-fix-v2"
TEXT_PRESET = "page-text-fix-v1"
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


def read_layout(png: str, ocr: Mapping[str, Any], model: str, dpi: int, run: RunFn = models_run) -> dict[str, Any]:
    """A page's layout as {model, groups, blocks: [{role, lines: [box, ...]}]}: the model's groups of numbered lines (what `rebuild_page`
    draws again) and, for the export, each block's role with its lines' boxes in page pixels, in reading order."""
    context = numbered(ocr, run)
    if not context:
        raise LayoutError("the page has no lines to lay out")
    params = {"preset": LAYOUT_PRESET, "context": context, "image": png, "max_tokens": 8192}
    groups = answer_json(run("vision-language", params, model))
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
) -> None:
    """The page set again as a PDF with real text at `out`, from its stored layout (`ocr["layout"]["groups"]`). `typed` is a person's text:
    it goes in as it stands, so a page whose typed lines are not the printed ones cannot be set line for line. `corrected` is the page's
    corrected text, whose lines go in where they are the printed ones (`with_corrected`)."""
    layout = cast("dict[str, Any]", ocr.get("layout") or {})
    groups = layout.get("groups")
    if not groups:
        raise LayoutError(str(layout.get("error") or "the page's layout has not been read: read the page again"))
    base = plain(ocr)
    context = numbered(ocr, run)
    if typed is None:
        params = {"preset": TEXT_PRESET, "context": context, "image": png, "max_tokens": 8192}
        texts = with_corrected(answer_json(run("vision-language", params, TEXT_MODEL)), corrected or "", context)
    else:
        texts = typed_texts(typed, context)
    fit = run("font-match", {"mode": "fit", "lines": base.get("lines") or [], "image": png, "dpi": dpi}, None)
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


READ_PRESET = "ocr-read-v2"


def read_again(png: str, run: RunFn = models_run) -> str:
    """The page's text read by the text model from the picture alone, with no OCR to lean on: what the gate checks a rebuilt page's words
    against. eval ocr-lines (2026-11-24, 20 hard pages): Haiku finds 99.8 % of the printed lines, 0.3 % of characters wrong, $0.0008 a page."""
    params = {"image": png, "prompt": "Transcribe this page.", "system_preset": READ_PRESET, "max_tokens": 4096}
    return str(run("vision-language", params, TEXT_MODEL).get("text") or "")


def with_corrected(texts: Mapping[str, Any], corrected: str, context: str) -> dict[str, Any]:
    """page-text-fix's answer with the page's corrected text in place of it on every line that is one of the text's. The correction reads a
    cleaned page (ocr-hard, 2026-11-24) and gets small capitals right that the line fix leaves misread ("PorrLy" for POLLY on the 1874 book);
    the lines the text leaves out (a running head, a page number) keep the line fix."""
    nums = [(int(m[1]), m[2]) for m in (NUMBERED.match(x) for x in context.splitlines()) if m]
    fixed = {int(x["n"]): str(x["text"]) for x in cast("list[dict[str, Any]]", texts.get("lines") or [])}
    lines = [x for x in corrected.splitlines() if x.strip()]
    for line, k in zip(lines, align(lines, [t for _, t in nums]), strict=True):
        if k is not None:
            fixed[nums[k][0]] = line
    return {**texts, "lines": [{"n": n, "text": t} for n, t in sorted(fixed.items())]}


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
