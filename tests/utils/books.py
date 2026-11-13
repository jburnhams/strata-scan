"""Small books made in the test, so every stage runs on real pictures and a real PDF without shipping scans: pages of real type drawn with
Pillow's bundled font, an "engraving" (a block of hatching, which Tesseract cannot read), a scanner bed round some pages, a tilt on one.
And `tesseract_ocr`, the ocr role's work done by the real `tesseract` command (installed in CI), for runs that do not go through the
strata-models service: it answers in the role's shape (stratamodels/runtimes/tesseract.py)."""

import csv
import io
import os
import random
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

W, H = 1240, 1754  # A5-ish at 150 dpi: big enough for Tesseract, small enough to be quick
TEXT = [
    "PUPPET-PLAYS IN ENGLAND. 27",
    "The minute fidelity of the puppets to the",
    "manners of his day led him in several places",
    "to introduce the name of a principal proprietor",
    "of puppet-shows, who was known by the title",
    "of Captain Pod. He mentions him in his works",
    "as well as in his Epigrams, from which it also",
    "appears that the word motion properly means",
    "the representation by puppets.",
]


def font(size=34):
    return ImageFont.load_default(size=size)


def page(lines=TEXT, picture=False, border=False):
    """One printed page: lines of type from the top margin, and a block of hatching under them when `picture`."""
    im = Image.new("RGB", (W, H), (236, 228, 212))
    d = ImageDraw.Draw(im)
    for i, t in enumerate(lines):
        d.text((120, 150 + 62 * i), t, fill=(30, 25, 20), font=font())
    if picture:
        rnd = random.Random(4)  # noqa: S311 (a fixed pattern, not a secret)
        x0, y0, x1, y1 = 260, 900, 980, 1550
        for k in range(0, (x1 - x0) + (y1 - y0), 9):
            d.line([(x0 + k, y0), (x0, y0 + k)], fill=(40, 35, 30), width=3)
        for _ in range(400):
            x, y = rnd.randint(x0, x1), rnd.randint(y0, y1)
            d.ellipse([x, y, x + 12, y + 12], fill=(20, 20, 20))
        d.rectangle([x0, y0, x1, y1], outline=(20, 20, 20), width=4)
        im.paste((236, 228, 212), (x1 + 1, y0, W, y1 + 1))
        im.paste((236, 228, 212), (x0, y1 + 1, x1 + 1, H))
    if border:
        d.rectangle([60, 60, W - 60, H - 60], outline=(30, 25, 20), width=4)
    return im


def on_bed(pg, angle=0.0, margin=160):
    """The page on a dark scanner bed, turned `angle` degrees counter-clockwise."""
    bed = Image.new("RGB", (pg.width + 2 * margin, pg.height + 2 * margin), (52, 48, 44))
    bed.paste(pg, (margin, margin))
    return bed.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(52, 48, 44)) if angle else bed


def cover():
    im = Image.new("RGB", (W + 320, H + 320), (40, 52, 44))
    ImageDraw.Draw(im).rectangle([600, 300, 900, 420], fill=(240, 240, 235))  # a library label
    return im


def book_pdf(path, scans=None):
    """A PDF of scans (default: cover, a tilted text page on a bed, a page with a picture, a full-bleed bordered page)."""
    scans = scans or [
        cover(),
        on_bed(page(), angle=1.5),
        on_bed(page(TEXT[:4], picture=True)),
        page(TEXT[1:], border=True),
    ]
    scans[0].save(path, "PDF", resolution=150.0, save_all=True, append_images=scans[1:])
    return path


def tesseract_ocr(path, pdf, lang, dpi=300):
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "p")
        env = dict(os.environ, OMP_THREAD_LIMIT="1")  # as the real runtime: one thread a page, pages side by side
        subprocess.run(
            ["tesseract", path, base, "-l", lang, "--psm", "3", "--dpi", str(dpi), "tsv", "pdf"],
            check=True,
            capture_output=True,
            env=env,
        )
        os.replace(base + ".pdf", pdf)
        with open(base + ".tsv", encoding="utf8") as f:
            rows = list(csv.DictReader(io.StringIO(f.read()), delimiter="\t", quoting=csv.QUOTE_NONE))
    lines, width, height = {}, 0, 0
    for r in rows:
        if r["level"] == "1":
            width, height = int(r["width"]), int(r["height"])
        if r["level"] != "5" or not (r.get("text") or "").strip():
            continue
        key = (int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))
        box = [int(r["left"]), int(r["top"]), int(r["width"]), int(r["height"])]
        lines.setdefault(key, []).append({"text": r["text"].strip(), "box": box, "conf": max(float(r["conf"]), 0.0)})
    out = []
    for key, ws in lines.items():
        x0, y0 = min(w["box"][0] for w in ws), min(w["box"][1] for w in ws)
        x1, y1 = max(w["box"][0] + w["box"][2] for w in ws), max(w["box"][1] + w["box"][3] for w in ws)
        out.append(
            {
                "text": " ".join(w["text"] for w in ws),
                "box": [x0, y0, x1 - x0, y1 - y0],
                "conf": sum(w["conf"] for w in ws) / len(ws),
                "block": key[0],
                "words": ws,
            }
        )
    return {
        "width": width,
        "height": height,
        "lines": out,
        "text": "\n".join(ln["text"] for ln in out),
        "model": "tesseract-eng",
        "pdf": pdf,
    }


def books_words(img_bgr):
    """The word boxes and confidences of a page, by the real tesseract (for figures.find_figures)."""
    import cv2

    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "p.png")
        cv2.imwrite(p, img_bgr)
        r = tesseract_ocr(p, os.path.join(tmp, "p.pdf"), "eng")
    return [(tuple(w["box"]), w["conf"]) for ln in r["lines"] for w in ln["words"]]
