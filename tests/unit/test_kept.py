"""kept.py: a cloud model's answer kept with its book and given again."""

from stratascan import kept


def test_an_answer_is_kept_and_given_again_and_a_fit_is_not_kept(tmp_path):
    asked = []

    def run(role, params, model):
        asked.append(role)
        return {"text": f"answer {len(asked)}"}

    keeping = kept.wrap(7, run)
    call = ("vision-language", {"image": "/p/1.png", "prompt": "fix"}, "claude-haiku-5-5-api")
    assert keeping(*call) == {"text": "answer 1"}
    assert keeping(*call) == {"text": "answer 1"}  # given again, not asked
    assert asked == ["vision-language"]
    other = ("vision-language", {"image": "/p/2.png", "prompt": "fix"}, "claude-haiku-5-5-api")
    assert kept.unasked(7, [call, other]) == [other]
    assert kept.unasked(8, [call]) == [call]  # another book's answers are its own
    fit = ("font-match", {"image": "/p/1.png"}, None)
    keeping(*fit)
    keeping(*fit)
    assert asked.count("font-match") == 2  # a fit runs here and follows strata-models' fixes: never kept
