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


def test_what_the_service_says_is_said_in_words(monkeypatch, fake_models):
    fake_models.results = {"font-match": {"face": "x"}}
    assert layout.models_run("font-match", {}, None) == {"face": "x"}
    fake_models.fail("out of memory")
    with pytest.raises(layout.LayoutError, match=r"could not do it \(font-match\): out of memory"):
        layout.models_run("font-match", {}, None)
    monkeypatch.setenv("STRATA_MODELS_URL", "http://127.0.0.1:9")
    with pytest.raises(layout.LayoutError, match="not running"):
        layout.models_run("font-match", {}, None)
