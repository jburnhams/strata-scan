import os

from app import __version__, greet, settings, system


def test_status_reports_versions_data_and_disk():
    greet.add_message("Ada")
    s = system.status()
    assert s["version"] == __version__
    assert s["python"].count(".") == 2
    assert s["data_dir"] == settings.data_dir()
    assert s["messages"] == 1
    assert s["data_bytes"] == sum(
        os.path.getsize(os.path.join(settings.data_dir(), f)) for f in os.listdir(settings.data_dir())
    )
    d = s["disk"]
    assert d["total"] > 0
    assert 0 <= d["used"] <= d["total"]
    assert 0 <= d["free"] <= d["total"]


def test_folder_bytes_sums_nested_files_and_skips_ones_that_vanish(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.bin").write_bytes(b"12345")
    (tmp_path / "y.bin").write_bytes(b"123")
    assert system.folder_bytes(str(tmp_path)) == 8
    real = os.path.getsize
    monkeypatch.setattr(
        os.path, "getsize", lambda p: (_ for _ in ()).throw(FileNotFoundError(p)) if p.endswith("y.bin") else real(p)
    )
    assert system.folder_bytes(str(tmp_path)) == 5
