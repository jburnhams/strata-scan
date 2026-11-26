"""marks.py on drawn pages: cream paper with handwriting, a stain, a speck and a red stamp; a book photographed on a dark backdrop."""

import colorsys

import cv2
import numpy as np

from stratascan import marks

CREAM = (180, 215, 230)  # BGR: the paper of the books this was made for


def page(tmp_path, name="p.png"):
    """A 1200 x 1800 leaf: cream paper browning towards its foot, a line of handwriting, a brown stain, a lone speck and a red stamp."""
    img = np.zeros((1800, 1200, 3), np.float32)
    img[:] = CREAM
    img *= np.linspace(1.0, 0.85, 1800)[:, None, None]  # darker towards the foot: the paper's tone, not a mark
    img = img.astype(np.uint8)
    for k in range(6):  # six letters of a word: each a short stroke, together a line of writing
        cv2.line(img, (300 + 40 * k, 400), (320 + 40 * k, 360), (70, 70, 80), 4)
    cv2.circle(img, (900, 1200), 60, (110, 160, 200), -1)  # the paper's colour, darker and stronger: a stain
    cv2.circle(img, (200, 1500), 3, (60, 60, 60), -1)  # a lone speck
    cv2.rectangle(img, (700, 300), (820, 420), (60, 60, 210), 6)  # a red stamp
    path = tmp_path / name
    cv2.imwrite(str(path), img)
    return str(path)


def paper_hue():
    h, _, _ = colorsys.rgb_to_hsv(CREAM[2] / 255, CREAM[1] / 255, CREAM[0] / 255)
    return h * 180


def test_the_writing_and_the_stamp_are_lifted_onto_white_and_the_stain_and_the_speck_are_not(tmp_path):
    png = page(tmp_path)
    hue = marks.paper_hue([png])
    assert hue is not None
    assert abs(hue - paper_hue()) < 2
    got = marks.lift(png, hue)
    out = got.image  # RGB
    assert out[380, 310].max() < 140  # the writing, dark
    assert out[300, 760][0] > 150  # the stamp, still red
    assert out[300, 760][1] < 120
    assert (out[1200, 900] == 255).all()  # the stain: the paper's own colour, taken away
    assert (out[1500, 200] == 255).all()  # the speck: alone, too small to be writing
    assert (out[1700, 600] == 255).all()  # the browner foot of the paper, white
    assert got.box is not None
    x, y, w, h = got.box
    assert x <= 300
    assert y <= 300
    assert x + w >= 820
    assert 420 <= y + h < 1000
    saved = marks.save(got, str(tmp_path / "m.png"))
    assert cv2.imread(saved).shape[:2] == (h, w)


def test_a_blank_leaf_has_no_marks_and_a_marbled_one_is_all_marks(tmp_path):
    blank = np.zeros((900, 600, 3), np.uint8)
    blank[:] = CREAM
    cv2.imwrite(str(tmp_path / "b.png"), blank)
    got = marks.lift(str(tmp_path / "b.png"), paper_hue())
    assert got.box is None
    assert got.share == 0
    marbled = np.random.default_rng(1).integers(0, 255, (900, 600, 3), dtype=np.uint8)
    marbled = cv2.resize(cv2.resize(marbled, (60, 90)), (600, 900), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(str(tmp_path / "m.png"), marbled)
    assert marks.lift(str(tmp_path / "m.png"), paper_hue()).share > marks.PATTERN


def test_the_book_is_found_on_its_backdrop_and_a_scan_with_none_is_left_alone(tmp_path):
    scan = np.full((1000, 800, 3), 30, np.uint8)  # a dark backdrop
    scan[100:900, 250:550] = (60, 90, 70)  # the book: dark green cloth, not far off the backdrop
    cv2.rectangle(scan, (300, 300), (500, 400), (40, 170, 200), -1)  # its gilt title
    behind = marks.backdrop(scan)
    assert behind is not None
    x, y, w, h = marks.book_box(scan, behind)
    assert abs(x - 250) < 15
    assert abs(y - 100) < 15
    assert abs(w - 300) < 25
    assert abs(h - 800) < 25
    leaf = np.random.default_rng(2).integers(0, 255, (400, 300, 3), dtype=np.uint8)  # cut to the page: no plain edge
    assert marks.backdrop(leaf) is None
    assert marks.book_box(leaf, None) is None
    cv2.imwrite(str(tmp_path / "spine.png"), scan[100:900, 250:550])
    assert marks.dark(str(tmp_path / "spine.png"))
    assert not marks.dark(page(tmp_path))
