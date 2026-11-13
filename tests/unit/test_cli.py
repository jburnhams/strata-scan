import importlib
import json

import pytest

from stratascan import cli


def test_doctor_success_and_missing_module(capsys, monkeypatch):
    assert cli.main(["doctor"]) == 0
    assert "fastapi" in capsys.readouterr().out

    real_import = importlib.import_module

    def fake_import(name):
        if name == "uvicorn":
            raise ImportError("no uvicorn")
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    assert cli.main(["doctor"]) == 1
    assert "MISSING  uvicorn" in capsys.readouterr().out


def test_add_books_run_and_export(capsys, tmp_path, models_service):
    """The CLI on a book made in the test, through the real strata-models client to a stand-in service that runs the real Tesseract."""
    from books import book_pdf

    assert cli.main(["books"]) == 0
    assert "no books yet" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="nothing at"):
        cli.main(["add", str(tmp_path / "none.pdf")])
    src = book_pdf(str(tmp_path / "Punch.pdf"))
    assert cli.main(["add", src, "--no-read"]) == 0
    out = capsys.readouterr().out
    assert "book 1: Punch (4 pages)" in out
    assert "import, detect in" in out
    assert cli.main(["run", "1", "read"]) == 0
    assert cli.main(["books", "--json"]) == 0
    capsys.readouterr()
    assert cli.main(["export", "1"]) == 0
    assert "book.zip" in capsys.readouterr().out
    assert cli.main(["books", "--json"]) == 0
    (row,) = json.loads(capsys.readouterr().out)
    assert {k: row[k] for k in ("id", "title", "stage", "pages", "read", "error")} == {
        "id": 1,
        "title": "Punch",
        "stage": "idle",
        "pages": 4,
        "read": 4,
        "error": None,
    }
    assert cli.main(["books"]) == 0
    assert "#1" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="no book 99"):
        cli.main(["run", "99", "read"])
    assert {j["params"]["dpi"] for j in models_service.submitted} == {150}


def test_set_and_serve_commands(capsys, monkeypatch):
    assert cli.main(["set", "workers"]) == 0
    assert "workers = 4" in capsys.readouterr().out

    assert cli.main(["set", "workers", "2"]) == 0
    assert "workers = 2" in capsys.readouterr().out

    assert cli.main(["set", "workers", "default"]) == 0
    assert "workers = 4" in capsys.readouterr().out

    with pytest.raises(SystemExit, match="unknown setting"):
        cli.main(["set", "bad_key", "val"])

    from stratascan.server import app as server_app

    called = []
    monkeypatch.setattr(server_app, "main", lambda argv: called.append(argv))
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert called == [["--host", "0.0.0.0", "--port", "9000"]]
