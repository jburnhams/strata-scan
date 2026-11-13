"""geometry.py on pictures made in the test: a page on a dark bed (straight and tilted), a page with no bed, a dark cover, a spread."""

import numpy as np
import pytest
from books import H, W, cover, on_bed, page
from PIL import Image

from stratascan import geometry as G


def bgr(im: Image.Image) -> np.ndarray:
    return np.asarray(im.convert("RGB"))[:, :, ::-1].copy()


def test_rotate_size_apply_and_clamp():
    img = np.zeros((100, 200, 3), np.uint8)
    assert G.rotate(img, 0) is img
    r = G.rotate(img, 90)
    assert r.shape[:2] == (200, 100)
    assert G.rotated_size(200, 100, 90) == (100, 200)
    assert G.rotated_size(200, 100, 0) == (200, 100)
    assert G.rotate(img, 30).shape[:2][::-1] == G.rotated_size(200, 100, 30)
    assert int(G.rotate(img, 30)[0, 0, 0]) == 255  # new corners are paper, not black
    assert G.clamp((-5, 90, 500, 50), 200, 100) == (0, 90, 200, 10)
    assert G.apply(img, 0, (10, 20, 30, 40)).shape == (40, 30, 3)
    assert G.gray(G.gray(img)).ndim == 2


@pytest.mark.parametrize("angle", [0.0, 1.5, -2.0])
def test_a_page_on_a_bed_is_found_and_levelled(angle):
    g = G.find_page(bgr(on_bed(page(), angle=angle)))
    assert g.side == "single"
    assert g.confidence > 0.9
    assert g.angle == pytest.approx(
        -angle, abs=0.35
    )  # PIL turns counter-clockwise for a positive angle: the page is undone by -angle
    _x, _y, w, h = g.crop
    assert abs(w - W) < 0.04 * W
    assert abs(h - H) < 0.04 * H


def test_a_page_with_no_bed_is_the_whole_scan():
    g = G.find_page(bgr(page(border=True)))
    assert g.crop == (0, 0, W, H)
    assert g.angle == 0.0
    assert g.confidence == 0.9


def test_a_dark_cover_is_kept_whole_with_low_confidence():
    img = bgr(cover())
    assert G.find_page(img) == G.PageGuess(0.0, (0, 0, img.shape[1], img.shape[0]), 0.2)
    assert G.find_pages(img)[0].side == "single"


def test_a_spread_is_split_at_its_gutter():
    left, right = page(), page()
    spread = Image.new("RGB", (2 * W, H))
    spread.paste(left, (0, 0))
    spread.paste(right, (W, 0))
    arr = np.asarray(spread).copy()
    arr[:, W - 40 : W + 40] = (arr[:, W - 40 : W + 40] * 0.5).astype(np.uint8)  # the fold's shadow
    pages = G.find_pages(bgr(on_bed(Image.fromarray(arr), angle=1.0)))
    assert [p.side for p in pages] == ["left", "right"]
    assert abs(pages[0].crop[2] - W) < 0.06 * W
    assert pages[1].crop[0] == pages[0].crop[0] + pages[0].crop[2]


def test_a_wide_page_with_no_gutter_stays_one_and_text_skew_needs_text():
    wide = Image.new("RGB", (2 * W, H), (236, 228, 212))
    assert len(G.find_pages(bgr(on_bed(wide)))) == 1
    blank = np.full((400, 300, 3), 230, np.uint8)
    assert G.text_skew(blank) is None
    assert G.gutter(blank) is None
    assert G.argbest([1.0, 3.0, 2.0]) == 1
    assert G.argbest([1.0, 3.0, 0.5], lowest=True) == 2


def test_an_empty_scan_is_kept_whole():
    black = np.zeros((300, 200, 3), np.uint8)
    g = G.find_page(black)
    assert g.crop == (0, 0, 200, 300)
    assert g.confidence == 0.5


def test_type_printed_askew_on_a_level_page_is_levelled_by_its_lines():
    # the paper's edges are square but the type is not (a page bound in crooked): the text lines decide the last fraction of a degree
    text = page().rotate(1.2, resample=Image.Resampling.BICUBIC, fillcolor=(236, 228, 212))
    g = G.find_page(bgr(on_bed(text, angle=0)))
    assert g.angle == pytest.approx(-1.2, abs=0.25)
    _x, _y, w, h = g.crop
    assert abs(w - W) < 0.04 * W
    assert abs(h - H) < 0.04 * H
