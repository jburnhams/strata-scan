import os

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app import greet, settings


def test_format_greeting_defaults_and_custom():
    assert greet.format_greeting() == {"name": "World", "greeting": "Hello", "message": "Hello, World!"}
    assert greet.format_greeting("  Alice  ", "  Hi ") == {"name": "Alice", "greeting": "Hi", "message": "Hi, Alice!"}
    assert greet.format_greeting("", "") == {"name": "World", "greeting": "Hello", "message": "Hello, World!"}


def test_format_greeting_validation():
    with pytest.raises(greet.GreetingError, match="name is too long"):
        greet.format_greeting("x" * 121)
    with pytest.raises(greet.GreetingError, match="greeting is too long"):
        greet.format_greeting("Alice", "g" * 61)


@given(
    name=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
    greeting=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
)
def test_format_greeting_property(name, greeting):
    res = greet.format_greeting(name, greeting)
    assert res["name"] == name.strip()
    assert res["greeting"] == greeting.strip()
    assert res["message"] == f"{greeting.strip()}, {name.strip()}!"


def test_message_log_persistence_and_clear():
    assert greet.list_messages() == []
    m1 = greet.add_message("Alice")
    m2 = greet.add_message("Bob", "Welcome")
    assert m1["id"] == 1
    assert m1["message"] == "Hello, Alice!"
    assert m2["id"] == 2
    assert m2["message"] == "Welcome, Bob!"
    msgs = greet.list_messages()
    assert [m["id"] for m in msgs] == [2, 1]

    assert greet.clear_messages() == {"cleared": 2}
    assert greet.list_messages() == []
    assert greet.clear_messages() == {"cleared": 0}


def test_list_messages_handles_corrupt_or_non_list_file():
    p = os.path.join(settings.data_dir(), "messages.json")
    with open(p, "w", encoding="utf8") as f:
        f.write("{bad json")
    assert greet.list_messages() == []
    with open(p, "w", encoding="utf8") as f:
        f.write('{"not": "a list"}')
    assert greet.list_messages() == []


def test_ids_are_never_reused_after_a_removal():
    a, b = greet.add_message("Alice"), greet.add_message("Bob")
    assert greet.remove_message(b["id"]) == b
    c = greet.add_message("Cy")
    assert c["id"] == 3
    assert [m["id"] for m in greet.list_messages()] == [3, 1]
    assert greet.remove_message(a["id"]) == a
    assert greet.remove_message(99) is None
    assert [m["name"] for m in greet.list_messages()] == ["Cy"]
    greet.remove_message(c["id"])  # the newest goes too: the next id still moves on
    assert greet.add_message("Di")["id"] == 4


def test_a_damaged_id_counter_falls_back_to_the_log():
    greet.add_message("Alice")
    greet.add_message("Bob")
    with open(os.path.join(settings.data_dir(), "messages.seq"), "w", encoding="utf8") as f:
        f.write("garbage")
    assert greet.add_message("Cy")["id"] == 3


def test_page_messages_goes_after_the_cursor_newest_first():
    for n in ("a", "b", "c", "d", "e"):
        greet.add_message(n)  # ids 1..5; the log is 5, 4, 3, 2, 1
    first = greet.page_messages(limit=2)
    assert [m["id"] for m in first["messages"]] == [5, 4]
    assert first["has_more"] is True
    assert [m["id"] for m in greet.page_messages(after=4, limit=2)["messages"]] == [3, 2]
    last = greet.page_messages(after=2, limit=2)
    assert [m["id"] for m in last["messages"]] == [1]
    assert last["has_more"] is False
    greet.remove_message(3)  # the cursor still works when its own greeting has gone
    assert [m["id"] for m in greet.page_messages(after=3, limit=5)["messages"]] == [2, 1]
    assert greet.page_messages(after=1) == {"messages": [], "has_more": False}
