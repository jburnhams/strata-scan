"""The command line on a book made in the test: add (import, find the pages, read them through the strata-models stand-in), list, run
one stage again, export; and the same entry point as a real process."""

import json
import os

from books import book_pdf

from stratascan import files, settings


def test_doctor_reports_the_environment(cli):
    r = cli("doctor", check=False)
    assert "strata-scan 0.1.0" in r.stdout
    assert "fastapi" in r.stdout
    assert r.code == 0


def test_a_book_from_the_command_line(cli, models_service, tmp_path):
    src = book_pdf(str(tmp_path / "punch.pdf"))
    out = cli("add", src, "--title", "Punch and Judy", "--author", "J. P. Collier").stdout
    assert "Punch and Judy" in out
    books = json.loads(cli("books", "--json").stdout)
    assert [(b["title"], b["pages"], b["stage"]) for b in books] == [("Punch and Judy", 4, "idle")]
    assert books[0]["read"] == 4
    assert len(models_service.jobs) >= 4  # every page went through the ocr role
    with open(os.path.join(files.book_dir(books[0]["id"]), "export", "book.md"), encoding="utf8") as f:
        md = f.read()
    assert md.startswith("# Punch and Judy\n\nJ. P. Collier")
    assert "puppets" in md
    cli("run", books[0]["id"], "export")
    assert "book.zip" in cli("export", books[0]["id"]).stdout
    r = cli("run", 99, "read", check=False)
    assert r.code != 0
    assert "no book 99" in r.out


def test_a_bad_source_is_refused_in_words(cli, tmp_path):
    (tmp_path / "notes.txt").write_text("not a book")
    r = cli("add", str(tmp_path / "notes.txt"), check=False)
    assert r.code != 0
    assert "notes.txt" in r.out


def test_settings_are_viewed_and_updated_from_the_command_line(cli, tmp_path, monkeypatch):
    monkeypatch.delenv("STRATASCAN_DATA", raising=False)
    elsewhere = tmp_path / "elsewhere"
    assert str(elsewhere) in cli("set", "data_dir", elsewhere).stdout
    assert settings.data_dir() == str(elsewhere.resolve())
    assert "data_dir" in cli("set", "data_dir", "default").stdout
    assert cli("set", "workers", "0", check=False).code != 0
    assert cli("set", "nope", "x", check=False).code != 0


def test_the_command_line_runs_as_a_real_process(cli_subprocess):
    assert "strata-scan 0.1.0" in cli_subprocess("doctor").stdout
    assert json.loads(cli_subprocess("books", "--json").stdout) == []
