"""Which printed line each line of a corrected text is. A correction keeps the print's line breaks, so its lines come in the order of the OCR's
lines, but not always one for one: a vision model joins two or drops a stain's line, and the text it corrects may come from another reading of
the page than the lines whose boxes are kept (pipeline.correct_page). So the two lists are aligned in order by likeness."""

from collections.abc import Sequence
from difflib import SequenceMatcher

LIKE = 0.45  # two lines at least this alike may be the same line (a badly read one still shares half its letters)


def letters(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def likeness(a: str, b: str) -> float:
    """0 to 1: how much of two lines' letters and digits agree, in order (spaces, case and punctuation are what OCR gets wrong)."""
    x, y = letters(a), letters(b)
    if not x or not y:
        return 0.0
    m = SequenceMatcher(None, x, y, autojunk=False)
    if m.real_quick_ratio() < LIKE or m.quick_ratio() < LIKE:
        return 0.0
    r = m.ratio()
    return r if r >= LIKE else 0.0


def align(new: Sequence[str], old: Sequence[str]) -> list[int | None]:
    """For each of `new`, the index of the line of `old` it is (each used at most once, in order), or None: the alignment whose likeness adds
    up to the most."""
    n, m = len(new), len(old)
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    like = [[likeness(a, b) for b in old] for a in new]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best[i][j] = max(best[i + 1][j], best[i][j + 1], best[i + 1][j + 1] + like[i][j])
    out: list[int | None] = []
    i = j = 0
    while i < n:
        if j < m and like[i][j] > 0 and best[i][j] == best[i + 1][j + 1] + like[i][j]:
            out.append(j)
            i, j = i + 1, j + 1
        elif j < m and best[i][j] == best[i][j + 1]:
            j += 1
        else:
            out.append(None)
            i += 1
    return out
