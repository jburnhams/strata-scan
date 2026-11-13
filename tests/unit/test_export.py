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
