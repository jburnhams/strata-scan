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
    # a line with no like goes with the line before it, so no word is lost
    p.text = ocr["corrected"]["text"] = "Punch and Judy\nby the author\na puppet show"
    assert [(ln["text"], ln["box"][1]) for ln in export.corrected_lines(p)] == [
        ("Punch and Judy", 100),
        ("by the author", 100),
        ("a puppet show", 140),
    ]
    # nothing like the OCR's lines: one block where the page's text began
    p.text = ocr["corrected"]["text"] = "Wholly different\nwords here"
    assert [(ln["text"], ln["box"][1]) for ln in export.corrected_lines(p)] == [
        ("Wholly different", 100),
        ("words here", 101),
    ]
    p.text = "typed over"  # the page's text is not the correction: the export uses the OCR lines as before
    assert export.corrected_lines(p) == []


def test_the_layout_says_what_is_a_heading_a_running_head_and_the_reading_order():
    from stratascan.db.models import Page

    ocr = {
        "lines": [
            line("PUPPETS 27", 100, 50, 800),
            line("CHAPTER I", 300, 100, 300),
            line("The puppets were made", 100, 140, 800),
            line("of wood and cloth", 100, 170, 400),
            line("stray", 100, 500, 100),
        ],
    }
    boxes = [ln["box"] for ln in ocr["lines"]]
    ocr["layout"] = {
        "blocks": [
            {"role": "running-head", "lines": [boxes[0]]},
            {"role": "heading", "lines": [boxes[1]]},
            {"role": "body", "lines": boxes[2:4]},
        ]
    }
    text = "\n".join(ln["text"] for ln in ocr["lines"])
    p = Page(book_id=1, scan_id=1, position=1, text=text, ocr=ocr, text_edited=False)
    md = export.page_markdown(p, [])
    assert "PUPPETS 27" not in md
    assert "## CHAPTER I" in md
    assert "The puppets were made of wood and cloth" in md
    assert "stray" in md  # a line in no block is kept, with the line before it
    ocr["layout"] = {"model": "m", "error": "spent"}  # no layout: by Tesseract's blocks, as before
    assert "##" not in export.page_markdown(p, [])


def laid_page(lines, blocks, **kw):
    from stratascan.db.models import Page

    ocr = {"lines": lines, "layout": {"blocks": blocks}, **kw}
    text = kw["corrected"]["text"] if "corrected" in kw else "\n".join(ln["text"] for ln in lines)
    return Page(book_id=1, scan_id=1, position=1, text=text, ocr=ocr, text_edited=False)


def test_a_body_line_the_layout_missed_is_not_dropped_with_the_running_head():
    lines = [
        line("PUPPETS 27", 100, 50, 800),
        line("the first sentence", 100, 100, 800),
        line("the second one", 100, 140, 800),
    ]
    blocks = [
        {"role": "running-head", "lines": [lines[0]["box"]]},
        {"role": "body", "lines": [lines[2]["box"]]},
    ]
    md = export.page_markdown(laid_page(lines, blocks), [])
    assert "PUPPETS" not in md
    assert md.index("the first sentence") < md.index("the second one")
    # nor a corrected line with no like among the OCR's lines, which borrows the running head's place
    fixed = {"model": "m", "text": "PUPPETS 27\nan added line of print\nthe second one", "lines": [0, 2]}
    md = export.page_markdown(laid_page(lines, blocks, corrected=fixed), [])
    assert "an added line of print" in md


def test_the_layouts_line_order_within_a_block_is_kept():
    lines = [line("the ending of it.", 100, 100, 800), line("The beginning and", 100, 140, 800)]
    blocks = [{"role": "body", "lines": [lines[1]["box"], lines[0]["box"]]}]
    assert "The beginning and the ending of it." in export.page_markdown(laid_page(lines, blocks), [])


def test_a_line_part_text_part_page_number_is_text():
    lines = [line("the last words 27", 100, 100, 800)]
    blocks = [
        {"role": "folio", "lines": [[860, 100, 40, 30]]},
        {"role": "body", "lines": [[100, 100, 500, 30]]},
    ]
    assert "the last words" in export.page_markdown(laid_page(lines, blocks), [])
