"""Calls queued ahead in bulk (stratascan.ahead) against the shared stand-in strata-models (the plugin's `fake_models`) over real HTTP."""

import pytest

from stratascan import ahead, layout


def test_planned_calls_go_in_one_bulk_call_per_role_and_model_and_answer_once(fake_models):
    fake_models.results = {"vision-language": lambda p: {"text": p["prompt"].upper()}, "page-build": {"text": "1 b1 x"}}
    bulk = ahead.Ahead()
    calls = [
        ("vision-language", {"prompt": "a"}, "haiku"),
        ("vision-language", {"prompt": "a"}, "haiku"),
        ("page-build", {}, None),
    ]
    assert bulk.send(calls) == 3
    assert [(j["role"], j["batch"]) for j in fake_models.jobs] == [("vision-language", None)] * 2 + [
        ("page-build", None)
    ]
    made = []

    def at_once(role, params, model):
        made.append(role)
        return {"text": "now"}

    run = bulk.wrap(at_once, lambda role, e: layout.LayoutError(f"{role}: {e}"))
    assert run("vision-language", {"prompt": "a"}, "haiku") == {"text": "A"}
    assert run("vision-language", {"prompt": "a"}, "haiku") == {"text": "A"}  # the second planned one
    assert run("vision-language", {"prompt": "a"}, "haiku") == {"text": "A"}  # none left: the answer already had
    assert made == []
    assert run("vision-language", {"prompt": "c"}, "haiku") == {"text": "now"}  # never planned: made now
    assert made == ["vision-language"]
    fake_models.jobs.clear()
    assert bulk.send([("vision-language", {"prompt": "d"}, "haiku")], batch=True) == 1
    assert [j["batch"] for j in fake_models.jobs] == [True]  # the batch API however few
    fake_models.fail("bad image", role="vision-language")
    bulk.send([("vision-language", {"prompt": "b"}, "haiku")])
    with pytest.raises(layout.LayoutError, match="vision-language: bad image"):
        run("vision-language", {"prompt": "b"}, "haiku")


def test_a_service_that_refuses_leaves_the_calls_to_be_made_at_once(fake_models, monkeypatch):
    bulk = ahead.Ahead()
    assert bulk.send([("no-such-role", {}, None)]) == 0
    monkeypatch.setenv("STRATA_MODELS_URL", "http://127.0.0.1:9")
    assert bulk.send([("vision-language", {}, None)]) == 0
    assert bulk.take("vision-language", {}, None) is None
