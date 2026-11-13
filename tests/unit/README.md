# Unit tests

Shared commands, layout, hermetic setup and file-ownership rules are in [`tests/README.md`](../README.md); read that first. This file is owned by unit-test work.

Fast and isolated: synthetic data and fakes; no external services, no network. `pytest tests/unit --cov` is what CI gates on (`fail_under` in `pyproject.toml`).

## Where things are tested

| Module | Tests | Coverage | Status | Notes |
| --- | --- | --- | --- | --- |
| `settings.py` | `test_settings.py` | 100% | done | home/data_dir/greeting defaults, overrides, save/load, corrupt JSON |
| `greet.py` | `test_greet.py` | 100% | done | formatting, length limits, hypothesis properties, message persistence, ids never reused, cursor paging, removing one |
| `system.py` | `test_system.py` | 100% | done | status snapshot, folder sizes (files that vanish mid-walk) |
| `cli.py` | `test_cli.py` | 100% | done | doctor, hello, messages, set, serve delegation |
| `server/app.py` | `test_server.py` | 100% | done | landing/static index, every page path with its relative `<base>`, health, system, settings, hello, messages (paged, remove one) endpoints |
