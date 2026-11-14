"""export.py: how printed lines become paragraphs, which lines are running heads, and the files a book gives."""

from stratascan import export


def line(text, x, y, w, block=1, h=30):
    return {"text": text, "box": [x, y, w, h], "block": block}


def test_join_lines_rejoins_split_words():
    assert export.join_lines(["the repre-", "sentation by", "", " puppets "]) == "the representation by puppets"
    assert export.join_lines(["Punch and-", "Judy"]) == "Punch and-Judy"  # a capital after the hyphen: a real hyphen


def test_paragraphs_break_at_indents_short_lines_and_blocks():
    lines = [
        line("It is singular that, to the present day, no", 100, 100, 800),
        line("attempt has been made to illustrate the", 100, 140, 800),
        line("origin of Mr. Punch.", 100, 180, 300),  # stops short: the paragraph ends
        line("His name and his performance are", 100, 220, 800),
        line("familiar to all.", 100, 260, 800),
        line("Another begins here, indented", 160, 300, 740),
        line("A footnote", 100, 900, 200, block=2),
    ]
    paras = export.paragraphs(lines)
    assert [t for _, t in paras] == [
        "It is singular that, to the present day, no attempt has been made to illustrate the origin of Mr. Punch.",
        "His name and his performance are familiar to all.",
        "Another begins here, indented",
        "A footnote",
    ]
    assert [y for y, _ in paras] == [100, 220, 300, 900]
    assert export.paragraphs([]) == []


def test_running_heads_and_page_numbers():
    assert export.is_running_head("PUPPET-PLAYS IN ENGLAND. 27", 20)
    assert not export.is_running_head("PUPPET-PLAYS IN ENGLAND. 27", 2)
    assert not export.is_running_head("the puppets were clothed as nearly as possible", 20)
    assert not export.is_running_head("27", 20)
    assert export.page_number("PUPPET-PLAYS IN ENGLAND. 27") == "27"
    assert export.page_number("4. PUNCH AND JUDY.") == "4"
    assert export.page_number("INTRODUCTION.") is None


def test_smaller_shrinks_only_big_pictures():
    from PIL import Image

    assert export.smaller(Image.new("L", (3000, 4000))).size == (1800, 2400)
    assert export.smaller(Image.new("RGB", (100, 50))).mode == "RGB"
    assert export.smaller(None).size == (1, 1)


def test_corrected_lines_take_the_place_of_the_ocr_lines_they_correct():
    from stratascan.db.models import Page

    ocr = {
        "lines": [
            line("Puncb and Judy", 100, 100, 800),
            line("~~ hatching ~~", 100, 300, 800),
            line("a puppet sbow", 100, 140, 600),
        ],
        "corrected": {"model": "m", "text": "Punch and Judy\na puppet show", "lines": [0, 2]},
    }
    p = Page(book_id=1, scan_id=1, position=1, text="Punch and Judy\na puppet show", ocr=ocr, text_edited=False)
    fixed = export.corrected_lines(p)
    assert [ln["text"] for ln in fixed] == ["Punch and Judy", "a puppet show"]
    assert [ln["box"] for ln in fixed] == [ocr["lines"][0]["box"], ocr["lines"][2]["box"]]  # where Tesseract found them
    # a correction that joined or split lines is still all there, as one block where the page's text began
    p.text = ocr["corrected"]["text"] = "Punch and Judy, a puppet show"
    assert [(ln["text"], ln["box"][1]) for ln in export.corrected_lines(p)] == [("Punch and Judy, a puppet show", 100)]
    p.text = "typed over"  # the page's text is not the correction: the export uses the OCR lines as before
    assert export.corrected_lines(p) == []
