from hypothesis import given
from hypothesis import strategies as st

from stratascan.align import align, likeness


def test_likeness_ignores_spacing_case_and_stray_marks():
    assert likeness("Mr. Punch, he said.", "MR PUNCH HE SAID") == 1.0
    assert likeness("The puppets", "~~~") == 0.0
    assert likeness("Puncb and Judv", "Punch and Judy") > 0.8
    assert likeness("a wholly other line", "of puppets") == 0.0


def test_align_keeps_the_order_and_leaves_out_what_is_not_there():
    old = ["Puncb and Judv", "~~ hatching ~~", "a puppet sbow", "of the streets"]
    assert align(["Punch and Judy", "a puppet show", "an added footnote", "of the streets"], old) == [0, 2, None, 3]
    assert align([], old) == []
    assert align(["Punch"], []) == [None]
    # a line joined from two goes to one of them, and the other is left out, never reordered
    got = align(["Punch and Judy a puppet show", "of the streets"], old)
    assert got[1] == 3


@given(st.lists(st.text(alphabet="abcdef ", max_size=12), max_size=8))
def test_align_of_a_list_with_itself_is_itself_where_it_has_letters(lines):
    out = align(lines, lines)
    assert all(k is None or k <= i + len(lines) for i, k in enumerate(out))
    assert [k for k in out if k is not None] == sorted(k for k in out if k is not None)
