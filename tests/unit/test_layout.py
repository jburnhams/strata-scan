import pytest

from stratascan import layout

OCR = {"width": 100, "height": 100, "text": "x", "lines": [{"text": "PUNCH", "box": [1, 2, 30, 10], "block": 1}]}


def run_with(**answers):
    calls = []

    def run(role, params, model):
        calls.append((role, params, model))
        return answers[role](params) if callable(answers[role]) else answers[role]

    run.calls = calls
    return run


def draw(params):
    if params.get("list_lines"):
        return {"text": "1 b1 [10,20,40,30] PUNCH"}
    return {"page": {"blocks": [{"role": "heading", "lines": [{"box": [1, 2, 30, 10]}]}]}}


def test_read_layout_keeps_the_groups_and_each_blocks_line_boxes():
    run = run_with(**{"page-build": draw, "vision-language": {"json": {"blocks": [{"lines": [1]}]}}})
    got = layout.read_layout("/p.png", {**OCR, "corrected": {"x": 1}}, "m", 500, run)
    assert run.calls[2][1]["dpi"] == 500  # the page pictures carry no dpi of their own
    assert got == {
        "model": "m",
        "groups": {"blocks": [{"lines": [1]}]},
        "blocks": [{"role": "heading", "lines": [[1, 2, 30, 10]]}],
    }
    assert "corrected" not in run.calls[0][1]["ocr"]  # only the OCR answer is sent on
    assert run.calls[1][1]["context"] == "1 b1 [10,20,40,30] PUNCH"


def test_a_json_answer_may_be_text_in_a_code_fence():
    fenced = chr(96) * 3 + 'json\n{"a": 1}\n' + chr(96) * 3
    assert layout.answer_json({"text": fenced}) == {"a": 1}
    with pytest.raises(layout.LayoutError, match="not JSON"):
        layout.answer_json({"text": "[1, 2]"})
    with pytest.raises(layout.LayoutError, match="not JSON"):
        layout.answer_json({"text": "nothing"})


@pytest.mark.parametrize(
    ("answers", "why"),
    [
        ({"page-build": {"text": ""}, "vision-language": {}}, "no lines"),
        ({"page-build": draw, "vision-language": {"json": {"blocks": []}}}, "found no blocks"),
        (
            {
                "page-build": lambda p: draw(p) if p.get("list_lines") else {"page": {"blocks": [{"role": "body"}]}},
                "vision-language": {"json": {"blocks": [{"lines": [99]}]}},
            },
            "hold none of the lines",
        ),
    ],
)
def test_an_empty_layout_is_an_error(answers, why):
    with pytest.raises(layout.LayoutError, match=why):
        layout.read_layout("/p.png", OCR, "m", 500, run_with(**answers))


def test_a_rebuild_without_a_layout_says_what_is_missing():
    run = run_with()
    with pytest.raises(layout.LayoutError, match="has not been read"):
        layout.rebuild_page("/p.png", OCR, "/o.pdf", 300, run=run)
    with pytest.raises(layout.LayoutError, match="budget"):
        layout.rebuild_page("/p.png", {**OCR, "layout": {"error": "the budget is spent"}}, "/o.pdf", 300, run=run)


def test_typed_text_is_sent_line_for_line_or_refused():
    context = "1 b1 [0,0,1,1] Puncb and Judv\n2 b1 [0,0,1,1] junk\n3 b1 [0,0,1,1] a puppet sbow"
    assert layout.typed_texts("Punch and Judy\n\na puppet show", context) == {
        "lines": [{"n": 1, "text": "Punch and Judy"}, {"n": 2, "text": ""}, {"n": 3, "text": "a puppet show"}]
    }
    with pytest.raises(layout.LayoutError, match="does not follow"):
        layout.typed_texts("Nothing like it at all\nwholly different", context)
    run = run_with(**{"page-build": {"text": context}, "font-match": {}, "vision-language": {}})
    layout.rebuild_page(
        "/p.png",
        {**OCR, "layout": {"groups": {"a": 1}}},
        "/o.pdf",
        300,
        "Punch and Judy",
        run,
    )
    assert [r for r, _, _ in run.calls] == [
        "page-build",
        "font-match",
        "page-build",
    ]  # a person's text is not corrected


def test_misread_words_are_put_right_from_the_corrected_text_and_the_lines_stay_the_prints():
    context = (
        "1 b1 [0,0,1,1] PUNCH AND JUDY. 9\n2 b1 [0,0,1,1] Porty.-I don't know.\n"
        "3 b1 [0,0,1,1] She repeats the let-\n4 b1 [0,0,1,1] ters to Puxciu and he"
    )
    fixed = {"lines": [{"n": 2, "text": "PorrLy.—I don't know."}], "note": 1}
    # the correction joins its lines, joins the split word and leaves the running head out
    corrected = "POLLY.—I don't know. She repeats the letters to Punch and he"
    assert layout.with_corrected(fixed, corrected, context) == {
        "lines": [{"n": 2, "text": "Polly.—I don't know."}, {"n": 4, "text": "ters to Punch and he"}],
        "note": 1,
    }
    assert layout.with_corrected({}, "", context) == {"lines": []}
    answers = {
        "page-build": {"text": context},
        "font-match": {},
        "vision-language": {"json": {"lines": []}, "text": "T"},
    }
    run = run_with(**answers)
    layout.rebuild_page("/p.png", {**OCR, "layout": {"groups": {"a": 1}}}, "/o.pdf", 300, None, run, corrected)
    assert run.calls[-1][1]["texts"]["lines"][-1] == {"n": 4, "text": "ters to Punch and he"}
    assert layout.read_again("/p.png", run) == "T"
    assert run.calls[-1][1]["system_preset"] == "ocr-read-v2"


def test_what_the_service_says_is_said_in_words(monkeypatch, fake_models):
    fake_models.results = {"font-match": {"face": "x"}}
    assert layout.models_run("font-match", {}, None) == {"face": "x"}
    fake_models.fail("out of memory")
    with pytest.raises(layout.LayoutError, match=r"could not do it \(font-match\): out of memory"):
        layout.models_run("font-match", {}, None)
    monkeypatch.setenv("STRATA_MODELS_URL", "http://127.0.0.1:9")
    with pytest.raises(layout.LayoutError, match="not running"):
        layout.models_run("font-match", {}, None)


def test_a_line_the_fix_emptied_is_kept_when_the_text_has_it_and_names_in_small_capitals_stay_so():
    context = "1 b1 [0,0,1,1] 29\n2 b1 [0,0,1,1] ADVERTISEMENTS.\n3 b2 [0,0,1,1] |\n4 b2 [0,0,1,1] Puxca.—What does"
    fixed = {"lines": [{"n": 1, "text": ""}, {"n": 3, "text": ""}, {"n": 4, "text": "PUNCH.—What does"}]}
    got = layout.with_corrected(fixed, "22\nADVERTISEMENTS.\nPUNCH.—What does", context)["lines"]
    assert {x["n"]: x["text"] for x in got} == {1: "22", 3: "", 4: "Punch.—What does"}
    assert layout.small_capitals("GOODS", "GOODS") == "GOODS"
    display = layout.with_corrected({}, "TOYS AND FANCY GOODS", "1 b1 [0,0,1,1] TOI AND EASCY Goons")["lines"]
    assert display == [{"n": 1, "text": "TOYS AND FANCY GOODS"}]


def test_lines_put_on_their_rows_are_never_left_out_of_the_layout_and_pictures_join_its_figures():
    laid = {
        "model": "m",
        "groups": {"blocks": [{"lines": [1], "role": "heading"}], "figures": [{"box": [0, 0, 9, 9]}]},
        "blocks": [{"role": "heading", "lines": [[10, 20, 100, 30]]}],
    }
    ocr = {
        "lines": [
            {"text": "A", "box": [10, 20, 100, 30], "block": 1001},
            {"text": "STRAW GOODS.", "box": [10, 90, 100, 30], "block": 1002},
            {"text": "junk", "box": [10, 190, 100, 30], "block": 7},
        ]
    }
    context = "1 b1001 [0,0,1,1] A\n2 b1002 [0,0,1,1] STRAW GOODS.\n3 b7 [0,0,1,1] junk"
    got = layout.with_left_out(laid, context, ocr)
    assert got["groups"]["blocks"] == [{"lines": [1], "role": "heading"}, {"lines": [2], "role": "body"}]
    assert got["blocks"] == [laid["blocks"][0], {"role": "body", "lines": [[10.0, 90.0, 100.0, 30.0]]}]
    figures = layout.with_pictures(laid, [[100, 50, 20, 10]], (500, 1000))["groups"]["figures"]
    assert figures[1] == {"kind": "ornament", "box": [100.0, 100.0, 120.0, 120.0]}


def test_a_tidied_page_whose_lines_are_numbered_otherwise_is_set_from_the_one_its_layout_was_read_from():
    def build(params):
        if params.get("list_lines"):
            return {"text": "\n".join(f"{n} b1 [0,0,1,1] x" for n, _ in enumerate(params["ocr"]["lines"]))}
        return {}

    run = run_with(**{"page-build": build, "font-match": {}, "vision-language": {"json": {"lines": []}}})
    was = {**OCR, "lines": OCR["lines"] * 2, "layout": {"groups": {"a": 1}}}
    layout.rebuild_page("/p.png", {**OCR, "layout": {"groups": {"a": 1}}}, "/o.pdf", 300, None, run, "", was)
    assert len(run.calls[-1][1]["ocr"]["lines"]) == 2


def lines_of(rows):
    """`numbered`'s list from (box in thousandths, text) rows."""
    return "\n".join(f"{n} b1 [{','.join(str(v) for v in box)}] {text}" for n, (box, text) in enumerate(rows, 1))


BODY = [
    ([150, 140 + 20 * i, 840, 156 + 20 * i], "the minute fidelity of the puppets to the manners") for i in range(14)
]


def test_a_plain_page_is_laid_out_from_its_own_lines():
    rows = [([400, 100, 580, 112], "PUNCH AND JUDY."), ([820, 100, 836, 112], "9"), *BODY]
    got = layout.plain_groups(lines_of(rows))
    assert got == {
        "blocks": [
            {"lines": [1], "role": "running-head"},
            {"lines": [2], "role": "folio"},
            {"lines": list(range(3, 17)), "role": "body"},
        ],
        "figures": [],
    }
    # a centred line alone between gaps is a heading; a gap parts the body; a streak read as a tall line is left out
    rows = [
        *rows[:2],
        *BODY[:7],
        ([440, 300, 560, 316], "Act II."),
        *[([b[0], b[1] + 60, b[2], b[3] + 60], t) for b, t in BODY[7:]],
    ]
    rows.append(([880, 90, 891, 160], "ee tna"))
    got = layout.plain_groups(lines_of(rows))["blocks"]
    assert [b["role"] for b in got] == ["running-head", "folio", "body", "heading", "body"]
    assert 18 not in [n for b in got for n in b["lines"]]


def test_a_page_of_few_lines_or_many_sizes_is_no_plain_page_and_a_lone_word_is_its_heading():
    assert layout.plain_groups(lines_of(BODY[:5])) is None
    mixed = [
        ([150, 100 + 40 * i, 840, 100 + 40 * i + (16 if i % 2 else 40)], "TOYS AND FANCY GOODS") for i in range(14)
    ]
    assert layout.plain_groups(lines_of(mixed)) is None
    assert layout.plain_groups(lines_of([([400, 100, 580, 116], "PREFACE."), *BODY])) is None  # a title, or a head?
    assert layout.plain_groups(lines_of([([380, 100, 600, 116], "CHAPTER II."), *BODY])) is None
    two = [([150, 140 + 20 * i, 480, 156 + 20 * i], "the minute fidelity of the puppets") for i in range(12)]
    two += [([520, b[1], 850, b[3]], t) for b, t in two]
    assert layout.plain_groups(lines_of(two)) is None


def test_a_plain_layout_asks_no_model():
    run = run_with(**{"page-build": draw})
    got = layout.read_layout("/p.png", OCR, "opus", 300, run, {"blocks": [{"lines": [1], "role": "body"}]})
    assert got["model"] == layout.PLAIN
    assert [c[0] for c in run.calls] == ["page-build", "page-build"]


def test_a_books_shortlist_is_sent_and_no_proposer_asked():
    run = run_with(
        **{
            "page-build": {"text": "1 b1 [0,0,1,1] x"},
            "font-match": {"proposed": ["a", "b"]},
            "vision-language": {"json": {"lines": []}},
        }
    )
    ocr = {**OCR, "layout": {"groups": {"a": 1}}}
    assert layout.rebuild_page("/p.png", ocr, "/o.pdf", 300, None, run, "", None, ["a", "b"]) == ["a", "b"]
    asked = next(c[1] for c in run.calls if c[0] == "font-match")
    assert (asked["candidates"], asked["propose"]) == (["a", "b"], False)
    layout.rebuild_page("/p.png", ocr, "/o.pdf", 300, None, run, "")
    assert "candidates" not in [c[1] for c in run.calls if c[0] == "font-match"][-1]


def test_a_reference_mark_the_line_fix_missed_is_put_in_from_the_corrected_text():
    context = "1 b1 [0,0,1,1] Dr. Faustus, the Queen\n2 b1 [0,0,1,1] of Sheba, and"
    got = layout.with_corrected({}, "Dr. Faustus,\u2020 the Queen\nof Sheba, and", context)["lines"]
    assert got == [{"n": 1, "text": "Dr. Faustus,\u2020 the Queen"}]
    assert not layout.same_word("Faustus,", "Faustus;")


def test_a_footnote_mark_read_as_a_plus_takes_the_corrected_texts_mark():
    context = "1 b1 [0,0,1,1] + Vol. iv. p. 427"
    got = layout.with_corrected({}, "\u2020 Vol. iv. p. 427", context)["lines"]
    assert got == [{"n": 1, "text": "\u2020 Vol. iv. p. 427"}]
    assert not layout.same_word("\u2020", "*")  # one mark for another: the line fix may be right
    assert not layout.same_word("-", "\u2014")
    assert layout.same_word("again.", "again.]")


def test_a_picture_page_is_its_pictures_on_clean_paper(tmp_path):
    from PIL import Image

    png = tmp_path / "p.png"
    Image.new("L", (1000, 2000), 200).save(png)
    run = run_with(**{"page-build": {}})
    layout.picture_page(str(png), [(100, 200, 500, 400)], str(tmp_path / "o.pdf"), 300, run)
    role, params, model = run.calls[0]
    assert (role, model) == ("page-build", layout.DRAW)
    (figure,) = params["groups"]["figures"]
    assert figure["box"] == [100.0, 100.0, 600.0, 300.0]
    assert Image.open(figure["image"]).mode == "L"  # an engraving in grey on white
    assert params["rules"]
    assert params["ocr"]["lines"] == []
    layout.picture_page(str(png), [], str(tmp_path / "b.pdf"), 300, run)  # nothing on it: a true blank
    assert run.calls[-1][1]["groups"]["figures"] == []
    colour = tmp_path / "c.png"
    im = Image.new("RGB", (400, 400), (230, 215, 180))
    im.paste((200, 30, 30), (100, 100, 300, 300))
    im.save(colour)
    out = layout.cut_picture(str(colour), (50, 50, 300, 300), str(tmp_path / "cut.png"))
    assert Image.open(out).mode == "RGB"
    assert Image.open(out).getpixel((150, 150))[1] < 80  # still red
    assert Image.open(out).getpixel((10, 10)) == (255, 255, 255)  # the paper made white


def test_pictures_are_jpegs_in_grey_unless_coloured(tmp_path):
    """An engraving on browned paper is a grey JPEG; a hand-coloured print stays in colour; a figure of the layout is given its own cut,
    and a rule is left to page-build."""
    from PIL import Image, ImageDraw

    page = Image.new("RGB", (1000, 1400), (225, 205, 165))  # browned paper
    d = ImageDraw.Draw(page)
    for y in range(120, 480, 6):  # an engraving's hatching, in brown-black ink
        d.line([(100, y), (500, y + 40)], fill=(60, 50, 40), width=2)
    d.rectangle([550, 700, 900, 1100], fill=(190, 40, 40))  # a coloured plate's red
    d.rectangle([600, 1150, 850, 1250], fill=(40, 70, 170))
    png = tmp_path / "p.png"
    page.save(png)
    grey = layout.cut_picture(str(png), (80, 100, 450, 450), str(tmp_path / "e.jpg"))
    with Image.open(grey) as im:
        assert (im.format, im.mode) == ("JPEG", "L")
        assert im.getpixel((5, 5)) > 240  # the paper white
    coloured = layout.cut_picture(str(png), (520, 650, 420, 650), str(tmp_path / "c.jpg"))
    with Image.open(coloured) as im:
        assert (im.format, im.mode) == ("JPEG", "RGB")
    groups = {
        "blocks": [],
        "figures": [{"box": [80, 70, 580, 400], "kind": "figure"}, {"box": [0, 500, 1000, 502], "kind": "rule"}],
    }
    got = layout.with_figure_pictures(groups, str(png), str(tmp_path / "crops"))
    fig, rule = got["figures"]
    assert fig["image"].endswith(".fig0.jpg")
    assert "image" not in rule
    assert layout.with_figure_pictures({"blocks": []}, str(png), str(tmp_path / "crops")) == {"blocks": []}
