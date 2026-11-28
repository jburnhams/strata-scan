"""qc.py on small PDFs made in the test (tests/utils/pdfs.py), each word its own text object as page-build draws them."""

from pdfs import scan_png, text_pdf
from PIL import Image, ImageDraw

from stratascan import qc

K = 200 / 72  # scan pixels a point at the test scans' 200 dpi


def words(y, texts, size=12, at=None, stroke=None):
    """A line of words at `y`, each its own object, laid out left to right (or at `at`)."""
    out, x = [], 40
    for i, t in enumerate(texts):
        out.append(
            (at[i] if at else x, y, t, size if not isinstance(size, list) else size[i], (stroke or [0] * len(texts))[i])
        )
        x += 8 * len(t) + 8
    return out


def test_uneven_weights_stray_sizes_and_words_over_others_are_found(tmp_path):
    good = text_pdf(tmp_path / "good.pdf", words(100, ["a", "plain", "line", "of", "running", "text", "here"]))
    page = qc.drawn(good, 400 * K)
    assert (qc.uneven_weight(page), qc.stray_words(page), qc.overlapping_words(page)) == (0, 0, 0)
    bold = text_pdf(
        tmp_path / "bold.pdf",
        words(100, ["the", "European", "sense", "of", "the", "term"], stroke=[0.3, 1.2, 1.2, 0.3, 0.3, 0.3]),
    )
    assert qc.uneven_weight(qc.drawn(bold, 400 * K)) == 1
    small = text_pdf(
        tmp_path / "small.pdf",
        words(100, ["secretly,", "away", "from", "the", "eyes", "of"], size=[8, 12, 12, 12, 12, 12]),
    )
    assert qc.stray_words(qc.drawn(small, 400 * K)) == 1
    advert = text_pdf(
        tmp_path / "advert.pdf", words(100, ["BIG", "small", "BIG", "small", "BIG"], size=[24, 10, 24, 10, 24])
    )
    assert qc.stray_words(qc.drawn(advert, 400 * K)) == 0  # several sizes on purpose
    over = text_pdf(tmp_path / "over.pdf", words(100, ["secre", "away", "from", "the"], at=[60, 66, 120, 170]))
    assert qc.overlapping_words(qc.drawn(over, 400 * K)) == 1


def test_pictures_missing_over_the_text_or_cut_short_and_an_oversized_page_are_found(tmp_path):
    pdf = text_pdf(tmp_path / "p.pdf", words(450, ["a", "line", "of", "text", "below"]))
    png = scan_png(tmp_path / "p.png", pdf)
    with Image.open(png) as im:
        d = ImageDraw.Draw(im)
        for x in range(200, 800, 6):  # an engraving, 200..800 x 150..700 pixels
            d.line([(x, 150), (x + 10, 700)], fill=30, width=2)
        im.save(png)
    page = qc.drawn(pdf, 400 * K)
    whole = (195.0, 145.0, 815.0, 705.0)
    page.pictures = [whole]
    assert qc.cut_short(page, png, []) == []
    page.pictures = [(195.0, 300.0, 815.0, 705.0)]  # its top lost
    assert qc.cut_short(page, png, []) == ["top"]
    page.pictures = []
    assert qc.missing_pictures(page, [whole]) == 1
    page.pictures = [whole]
    assert qc.missing_pictures(page, [whole]) == 0
    assert qc.text_under_pictures(page, [(100.0, 650.0, 900.0, 690.0)]) == 1  # a line of text the picture runs over
    assert qc.text_under_pictures(page, [(100.0, 1100.0, 900.0, 1150.0)]) == 0
    assert qc.oversized(pdf, page) == []
    page.size = (2324.0, 3224.0)  # a page given as its pixels at 72 dpi
    assert qc.oversized(pdf, page) == ["the page is 32 by 45 inches"]
    looked = qc.look(pdf, png, 400 * K, [(100.0, 650.0, 900.0, 690.0)], [whole])
    assert looked == ["1 pictures the read found are not drawn"]
