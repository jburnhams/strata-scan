import numpy as np
import pytest
from pdfs import DPI, blocks_of, scan_png, text_pdf

from stratascan import gate

LINES = [
    (30, 60, "The minute fidelity of the puppets to the"),
    (30, 100, "manners of his day led him in several places"),
    (30, 140, "to introduce the name of a principal † proprietor"),
    (30, 180, "of puppet-shows, who was known by the title"),
]
TEXT = "\n".join(t for _, _, t in LINES)


def check(tmp_path, lines, text=TEXT, scanned=LINES):
    scan = text_pdf(tmp_path / "scan.pdf", scanned)
    png = scan_png(tmp_path / "scan.png", scan)
    pdf = text_pdf(tmp_path / "rebuilt.pdf", lines)
    return gate.check_page(pdf, png, text, blocks_of(scanned), DPI)


def test_a_page_set_as_it_was_printed_passes(tmp_path):
    v = check(tmp_path, LINES)
    assert v.passed
    assert v.record()["reasons"] == []
    assert (v.words_lost, v.overlap, v.off_page, v.symbols_lost) == (0.0, 0.0, 0, ())
    assert v.ink > 0.95


def test_a_line_left_out_fails_on_words_and_ink(tmp_path):
    v = check(tmp_path, LINES[:3])
    assert any("of the words are missing" in r for r in v.reasons)
    assert v.words_lost == pytest.approx(8 / 35, abs=0.1)
    assert v.record()["passed"] is False


def test_a_line_drawn_over_another_fails(tmp_path):
    v = check(tmp_path, [*LINES, (34, 62, "a wholly different line drawn upon the first")])
    assert any("lie over others" in r for r in v.reasons)


def test_text_off_the_page_fails(tmp_path):
    v = check(tmp_path, [*LINES, (390, 220, "and more words of it", 18)])
    assert v.off_page > 0
    assert any("off the page" in r for r in v.reasons)


def test_a_page_set_in_the_wrong_place_fails_on_ink(tmp_path):
    v = check(tmp_path, [(x + 12, y + 12, t) for x, y, t in LINES])
    assert v.ink < gate.INK
    assert any("ink agrees" in r for r in v.reasons)


def test_a_symbol_the_font_lacks_fails_by_name(tmp_path):
    v = check(tmp_path, [(x, y, t.replace("†", "")) for x, y, t in LINES])
    assert v.symbols_lost == ("†",)
    assert any("symbols are missing: †" in r for r in v.reasons)


def test_curly_quotes_dashes_and_split_words_are_not_losses(tmp_path):
    lines = [(30, 60, "“puppet” — he said"), (30, 100, "of the repre-"), (30, 140, "sentation")]
    v = check(tmp_path, lines, text='"puppet" - he said\nof the representation', scanned=lines)
    assert v.words_lost == 0
    assert v.symbols_lost == ()


def test_a_page_with_no_words_or_no_pdf_never_passes(tmp_path):
    png = scan_png(tmp_path / "s.png", text_pdf(tmp_path / "s.pdf", LINES))
    assert (
        gate.check_page("/nope.pdf", png, TEXT, [], DPI).reasons[0].startswith("the rebuilt page could not be checked")
    )
    assert not gate.check_page(str(tmp_path / "s.pdf"), png, " \n", [], DPI).passed
    assert not gate.check_page(str(tmp_path / "s.pdf"), str(tmp_path / "no.png"), TEXT, [], DPI).passed


def test_pages_with_no_ink_agree_and_one_side_without_it_does_not():
    a, b, where = np.zeros((9, 9), bool), np.zeros((9, 9), bool), np.ones((9, 9), bool)
    assert gate.ink_f1(a, b, 1, where) == 1.0
    b[4, 4] = True
    assert gate.ink_f1(a, b, 1, where) == 0.0
    assert gate.ink_f1(b, b, 1, where) == 1.0
    assert gate.overlapping([]) == 0
