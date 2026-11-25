import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from stratascan import rows

DPI = 200
W, H = 1200, 900


def font(size):
    return ImageFont.load_default(size=size)


def page(lines, frame=True):
    """A printed page (gray): (x, y, text, size[, hollow]) each, inside a frame of double rules; and the OCR answer of its lines."""
    im = Image.new("L", (W, H), 225)
    d = ImageDraw.Draw(im)
    if frame:
        for m in (40, 52):
            d.rectangle([m, m, W - m, H - m], outline=30, width=3)
    ocr = []
    for x, y, text, size in lines:
        d.text((x, y), text, fill=25, font=font(size))
        words, at = [], x
        for w in text.split():
            b = d.textbbox((at, y), w, font=font(size))
            words.append({"text": w, "box": [int(b[0]), int(b[1]), int(b[2] - b[0]), int(b[3] - b[1])], "conf": 95.0})
            at = d.textlength(w + " ", font=font(size)) + at
        x0, y0 = min(w["box"][0] for w in words), min(w["box"][1] for w in words)
        x1 = max(w["box"][0] + w["box"][2] for w in words)
        y1 = max(w["box"][1] + w["box"][3] for w in words)
        ocr.append({"text": text, "box": [x0, y0, x1 - x0, y1 - y0], "conf": 95.0, "block": 1, "words": words})
    return np.asarray(im, dtype=np.uint8), {"width": W, "height": H, "text": "", "lines": ocr}


ADVERT = [
    (150, 100, "ADVERTISEMENTS.", 28),
    (150, 170, "FRENCH AND GERMAN", 60),
    (150, 290, "STRAW GOODS.", 70),
    (150, 420, "No. 926 Market Street,", 36),
    (150, 500, "PHILADELPHIA.", 48),
]
TEXT = "\n".join(t for _, _, t, _ in ADVERT)


def test_rows_are_the_printed_lines_and_the_frame_is_none():
    gray, _ = page(ADVERT)
    found = rows.find_rows(gray, DPI)
    assert len(found) == len(ADVERT)
    assert all(r.box[0] > 60 and r.box[0] + r.box[2] < W - 60 for r in found)
    assert rows.find_rows(np.full((H, W), 225, dtype=np.uint8), DPI) == []


def test_a_page_the_ocr_read_well_is_left_as_it_is():
    gray, ocr = page(ADVERT)
    assert rows.repair(ocr, gray, TEXT, DPI) == (ocr, 0)
    assert rows.repair(ocr, gray, "", DPI) == (ocr, 0)


def test_a_line_the_ocr_missed_is_put_on_its_row_word_by_word():
    gray, ocr = page(ADVERT)
    missed = ocr["lines"].pop(2)
    got, n = rows.repair(ocr, gray, TEXT, DPI)
    assert n == 1
    assert [ln["text"] for ln in got["lines"]] == [t for _, _, t, _ in ADVERT]
    new = got["lines"][2]
    assert [w["text"] for w in new["words"]] == ["STRAW", "GOODS."]
    for w, was in zip(new["words"], missed["words"], strict=True):
        assert w["box"][0] == pytest.approx(was["box"][0], abs=14)
        assert w["box"][2] == pytest.approx(was["box"][2], rel=0.15)


def test_a_line_boxed_with_the_frame_or_read_as_other_words_is_replaced():
    gray, ocr = page(ADVERT)
    line = ocr["lines"][1]
    line["box"] = [44, line["box"][1], line["box"][0] + line["box"][2] - 44, line["box"][3]]
    ocr["lines"][4]["text"] = "xqz zzz"
    got, n = rows.repair(ocr, gray, TEXT, DPI)
    assert n == 2
    assert got["lines"][1]["box"][0] > 100
    assert got["lines"][4]["text"] == "PHILADELPHIA."


def test_a_letter_outside_every_words_box_makes_the_line_bad():
    gray, ocr = page(ADVERT)
    first = ocr["lines"][1]["words"][0]
    first["box"] = [first["box"][0], first["box"][1], first["box"][2] // 2, first["box"][3]]
    _, n = rows.repair(ocr, gray, TEXT, DPI)
    assert n == 1


def test_a_text_that_joined_the_prints_lines_is_not_put_on_one_row():
    body = [(120, 100 + 60 * i, "the minute fidelity of the puppets to the", 30) for i in range(5)]
    gray, ocr = page(body)
    joined = " ".join(t for _, _, t, _ in body)
    del ocr["lines"][2]
    assert rows.repair(ocr, gray, joined, DPI) == (ocr, 0)


def test_tidy_drops_the_frame_read_as_a_word_and_cuts_boxes_to_the_row_without_moving_lines():
    gray, ocr = page(ADVERT)
    line = ocr["lines"][3]
    high = line["box"][3]
    line["words"].insert(0, {"text": "|", "box": [42, line["box"][1], 6, 30], "conf": 40.0})
    line["words"][-1]["box"][2] += 500
    line["text"] = "| " + line["text"]
    got = rows.tidy(ocr, gray, DPI)["lines"]
    assert len(got) == len(ocr["lines"])
    assert got[3]["text"] == "No. 926 Market Street,"
    assert got[3]["words"][0]["text"] == "No."
    assert got[3]["words"][-1]["box"][0] + got[3]["words"][-1]["box"][2] < 1100
    assert got[3]["box"][3] == high  # strata-models splits a line by its height
    assert got[0] == ocr["lines"][0]


def test_a_picture_mark_is_cut_from_the_scan_not_set():
    assert rows.picture_mark("☞")
    assert not rows.picture_mark("A")
    assert not rows.picture_mark("†")  # a dagger is type
    lines = [
        (230, 120, "MAGIC LANTERNS AND SLIDES", 40),
        (150, 220, "FRENCH AND GERMAN", 60),
        (150, 340, "No. 926", 40),
    ]
    gray, ocr = page(lines)
    out = gray.copy()
    cv2.rectangle(out, (150, 130), (200, 155), 25, -1)  # the hand
    del ocr["lines"][0]
    got, n = rows.repair(ocr, out, "☞ MAGIC LANTERNS AND SLIDES\nFRENCH AND GERMAN\nNo. 926", DPI)
    assert n == 1
    assert got["lines"][0]["text"] == "MAGIC LANTERNS AND SLIDES"
    assert len(got["pictures"]) == 1
    assert got["pictures"][0][0] == pytest.approx(150, abs=6)


def test_words_of_a_row_with_fewer_marks_than_words_share_its_width():
    row = rows.Row((0, 0, 100, 20), ((0, 0, 40, 20), (60, 0, 40, 20)))
    words = rows.split_words(row, "a bb c")
    assert [w["text"] for w in words] == ["a", "bb", "c"]
    assert words[0]["box"][0] == 0
