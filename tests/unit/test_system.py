import os

import pytest

from stratascan import pipeline, settings, system


def test_status_reports_versions_data_disk_and_strata_models(http_server, monkeypatch):
    monkeypatch.setenv("STRATA_MODELS_URL", http_server.url)
    http_server.route("GET", "/api/health", {"ok": True})
    http_server.route("GET", "/api/registry", {"roles": [{"key": "ocr", "model": "tesseract-eng"}]})
    s = system.status()
    assert s["data_dir"] == settings.data_dir()
    assert s["python"].count(".") == 2
    assert s["models"] == {"url": http_server.url, "available": True, "ocr_model": "tesseract-eng"}
    d = s["disk"]
    assert d["total"] > 0
    assert 0 <= d["used"] <= d["total"]


def test_without_strata_models(monkeypatch):
    monkeypatch.setenv("STRATA_MODELS_URL", "http://127.0.0.1:9")
    assert system.models() == {"url": "http://127.0.0.1:9", "available": False, "ocr_model": None}


def test_ocr_through_the_client(http_server, monkeypatch, tmp_path):
    """models_ocr sends the role's params and returns its answer; a failed job and a missing service become words."""
    monkeypatch.setenv("STRATA_MODELS_URL", http_server.url)
    http_server.route("POST", "/api/jobs", {"id": 5, "status": "queued"})
    http_server.route(
        "GET", "/api/jobs/5", {"id": 5, "status": "done", "result": {"text": "Punch", "lines": []}}, once=True
    )
    assert pipeline.models_ocr("/p.png", "/p.pdf", "eng", 360) == {"text": "Punch", "lines": []}
    assert http_server.requests[0].json() | {} == {
        "role": "ocr",
        "params": {"path": "/p.png", "pdf": "/p.pdf", "lang": "eng", "dpi": 360},
        "app": "strata-scan",
        "priority": "batch",
        "model": None,
        "options": None,
    }
    http_server.route("GET", "/api/jobs/5", {"id": 5, "status": "failed", "error": "no such picture"})
    with pytest.raises(pipeline.StageError, match="could not read the page: no such picture"):
        pipeline.models_ocr("/p.png", "/p.pdf", "eng", 360)
    monkeypatch.setenv("STRATA_MODELS_URL", "http://127.0.0.1:9")
    with pytest.raises(pipeline.StageError, match="strata-models is not running"):
        pipeline.models_ocr("/p.png", "/p.pdf", "eng", 360)


def test_folder_bytes_sums_nested_files_and_skips_ones_that_vanish(tmp_path, monkeypatch):
    root = tmp_path / "f"  # tmp_path itself holds the test's database
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.bin").write_bytes(b"12345")
    (root / "y.bin").write_bytes(b"123")
    assert system.folder_bytes(str(root)) == 8
    real = os.path.getsize
    monkeypatch.setattr(
        os.path, "getsize", lambda p: (_ for _ in ()).throw(FileNotFoundError(p)) if p.endswith("y.bin") else real(p)
    )
    assert system.folder_bytes(str(root)) == 5
