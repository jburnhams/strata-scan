"""figures.py: a hatched block on a page of type is a picture, the type and a printed border are not."""

import numpy as np
from books import TEXT, books_words, page

from stratascan import figures as F


def arr(im):
    return np.asarray(im)[:, :, ::-1].copy()


def test_the_engraving_is_found_and_the_type_and_border_are_not():
    img = arr(page(TEXT[:4], picture=True, border=True))
    boxes = F.find_figures(img, books_words(img))
    assert len(boxes) == 1
    x, y, w, h = boxes[0]
    assert abs(x - 260) < 30
    assert abs(y - 900) < 30
    assert abs(w - 720) < 50
    assert abs(h - 650) < 50


def test_a_page_of_type_has_no_pictures():
    img = arr(page(border=True))
    assert F.find_figures(img, books_words(img)) == []


def test_low_confidence_words_do_not_cut_a_picture_and_boxes_merge_and_pad():
    img = arr(page(TEXT[:4], picture=True))
    nonsense = [((300, 950, 200, 40), 12.0), ((600, 1200, 200, 40), 30.0)]  # Tesseract "reading" the engraving
    assert len(F.find_figures(img, nonsense)) == 1
    assert F.merge([(0, 0, 10, 10), (5, 5, 10, 10), (50, 50, 5, 5)]) == [(0, 0, 15, 15), (50, 50, 5, 5)]
    assert F.pad_box((5, 5, 10, 10), 100, 100) == (4, 4, 12, 12)
    assert F.pad_box((0, 0, 100, 100), 100, 100) == (0, 0, 100, 100)
