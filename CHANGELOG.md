# Changelog

Newest first, grouped by day. One entry per change, in the same commit or PR as the change.

## 2026-11-13

**strata-scan: scanned books to pages, text, pictures and a searchable PDF; backend and CLI (branch `claude/project-thread-0n1ijc`)**
Jonathan asked to turn this repo (until now a copy of python-app-template) into a web app for processing two scanned books: rotate, crop, extract text and pictures, OCR, with model work in strata-models and screens from strata-react. This entry is the backend, CLI, tests and deploy files; the web app follows on the same branch.

- `src/app` -> `src/stratascan`, `app`/`app.cmd` -> `strata-scan`/`strata-scan.cmd`; `pyproject.toml`: name `strata-scan`, script `strata-scan`, port 8368, dependencies opencv-python-headless, numpy, pypdfium2, pypdf, pillow, python-multipart, omarchy-db and strata-models-client (git sources), `[tool.omarchy-db]`, plugin tuning variables. `uv.lock`.
- `src/app/greet.py`, `tests/unit/test_greet.py`: removed with the greetings sample.
- `settings.py`: `data_dir`, `max_dpi` (600), `workers` (4).
- `db/models.py`, `migrations/20261113_85a64741b9b6_initial.py`, `store.py`: **new**; books, scans, pages, figures in schema `stratascan` (defaults written portably by hand: `sa.false()`, `CURRENT_TIMESTAMP`).
- `files.py`, `sources.py`, `geometry.py`, `figures.py`, `pipeline.py`, `export.py`: **new**; the folder layout, import, page finding, picture finding, the four stages and their runner, the exports. Why each threshold is what it is: `docs/progress.md`.
- `server/app.py`: the books/pages/scans/figures API (listed in its docstring); the greetings routes removed. `server/landing.html`: lists the books when the web app is not built. `system.py`: data folder size and whether strata-models has the `ocr` role. `cli.py`: `add`, `books` (`--json` is the API's book shape), `run`, `export`; `run` on a missing book says so.
- `tests/utils/books.py`, `tests/utils/models_service.py`: **new**; synthetic books (real type, an engraving, a scanner bed, a tilt, a cover) and a strata-models stand-in that runs the real `tesseract`. `tests/conftest.py`: a fresh database per test (`db_env`), `runner`, `make_book`, `models_service`.
- `tests/unit/test_{geometry,figures,sources,pipeline,export,server}.py`: **new**; `test_{cli,settings,system,version}.py` rewritten. 45 tests, 96% coverage.
- `tests/integration/`: rewritten for the CLI (a book added, read and exported through the stand-in) and the API on a real server (`live_app`: upload, wait, re-crop, typed text survives a re-read, hand-drawn picture, zip download).
- `.github/workflows/unit.yml`, `integration.yml`: install Tesseract on Linux, macOS and Windows; `dbtool check` once.
- `deploy/app.service` -> `deploy/strata-scan.service` (database and strata-models variables), `deploy/strata-scan.caddy` **new**; `docs/deploying.md`: the database and strata-models steps.
- `README.md`, `AGENTS.md`, `tests/README.md`, `docs/overview.md`, `docs/implementation-plan.md`, `docs/progress.md`: describe strata-scan instead of the template sample.

## 2026-11-09

**Regenerate visual baselines on the CI runner (branch `claude/project-thread-iw7199`)**
Jonathan wants every dependency kept current, including Dependabot's playwright and lucide-react bumps. Those change the Chromium or the icons behind every screenshot, and a laptop cannot reproduce the CI Chromium, so the baselines are now written by a manual workflow.

- `.github/workflows/update-visual-baselines.yml`: **new**; manual run on a chosen branch: `test:visual:update`, then `test:visual` to prove stability, then commits `web/tests/visual/baselines` to that branch.
- `AGENTS.md`: CI section mentions it.

**Move onto the strata-python library (branch `claude/project-thread-iw7199`)**
Jonathan asked for the shared server code to live in a `strata-python` project (like strata-react) so the template stops duplicating it, and for apps to track its latest. This replaces the template's own copies; behaviour is unchanged except where noted.

- `pyproject.toml`, `uv.lock`: depend on `strata-python` as a git source tracking `main` (the lock pins the commit); pytest options `strata_env_prefix`/`strata_tuning_vars` configure the library's plugin.
- `src/app/oslib.py`, `scripts/check.py`, `tests/utils/http_server.py`, `tests/unit/test_oslib.py`, `tests/unit/test_http_server.py`: **removed**, now `strata_python.oslib`, `strata-check` and the plugin's `http_server` fixture (the library tests them, with real processes and sockets).
- `src/app/settings.py`: declares the two settings with `strata_python.settings.Settings`; same files and `APP_*` variables. Corrections: a bad `data_dir` or blank greeting now raises ValueError from `save` (the API answers 400, as it did for a relative path), `~` in `data_dir` is expanded when saved, and a bad stored or environment value falls back to the default instead of crashing.
- `src/app/server/app.py`, `src/app/cli.py`: health, settings and page routes, `serve`, `doctor` and `set` come from the library; the app keeps its own routes and `hello`/`messages`.
- `tests/conftest.py`: hermetic environment, no-network guard and `http_server` fixture removed (plugin). The `fake_*` fixtures stay as last resorts.
- `scripts/check`, `.github/workflows/unit.yml`: run `strata-check`. `.github/workflows/upgrade-strata-python.yml` **new**: weekly lock upgrade that runs the gate and opens a PR.
- `AGENTS.md`, `README.md`: describe the library, the tracking-main rule and the upgrade workflow.

**Testing policy: real code over mocks (branch `claude/project-thread-iw7199`)**
Asked to steer tests away from mocks towards real HTTP, embedded databases and installed tools, and to make skipping deliberate.

- `AGENTS.md`: **new** Testing policy section (real by default; mocks only for true externals in quick many-case unit tests; install ffmpeg and the like instead of mocking; no silent skips, a skip is a marker with a reason and a switch; machine-heavy tests are marked and run where the machine is).
- `tests/utils/http_server.py`, `tests/unit/test_http_server.py`: **new**. A real loopback HTTP server scripted per test (`http_server` fixture in `tests/conftest.py`); a request no route answers fails the test at teardown.
- `tests/utils/fakes.py`: docstring marks the doubles as a last resort. `tests/README.md`: layout notes point to the policy.
- `pyproject.toml`: ruff `TID` rules selected, `pytest.importorskip` banned with the reason.

**AGENTS.md reorganised as the basis for apps made from the template (branch `claude/project-thread-iw7199`)**
Asked to make the agent instructions suitable as the starting point for future apps, and to point database work at the shared database project.

- `AGENTS.md`: regrouped into rules for every change (run `scripts/check`, changelog and docs in the same commit, comment the why, no secrets or machine-specific details, strict types, tests, report what was run), layout, Python tooling, tests, web, CI and a closing checklist. Says which parts to keep unchanged in a derived app. Content of the earlier bullets is kept.
- `AGENTS.md`: **new** Database section. Apps use [jburnhams/database](https://github.com/jburnhams/database) (one shared database, one schema per app, models and migrations in the app repo, `dbtool check` in CI, never one database per app) and link its adoption guide rather than repeating it.

**Generic deployment notes and a systemd unit example (branch `claude/project-thread-iw7199`)**
A Docker image was dropped from the plan because apps are not deployed that way. These files are deliberately free of machine-specific details.

- `deploy/app.service`: **new**. Example systemd user unit running `uv run --locked --no-dev app serve`.
- `docs/deploying.md`: **new**. Build, install, run, reverse-proxy and how to keep a service file in step with the repo.
- `AGENTS.md`: points to them; the stale `setup_env` mention is gone (corrects the earlier line left behind by the uv change).

**Move the Python side to uv, typed strict, one gate (branch `claude/project-thread-iw7199`)**
Asked for an evaluation of this template against current best practice; the tooling gaps it found are closed here. Behaviour of the app is unchanged.

- `pyproject.toml`: now a real project (`[project]`, hatchling build, `app` console script, `[dependency-groups] dev`), with `--strict-markers --strict-config` for pytest, ruff rules `E,F,I,B,UP,SIM,RUF,C4,PT,S` at line length 120, and pyright strict.
- `uv.lock`, `.python-version`: **new**. Builds are reproducible; CI installs with `uv sync --locked`.
- `requirements.txt`, `requirements-test.txt`, `scripts/setup_env.sh`, `scripts/setup_env.ps1`: **removed**; `uv sync` replaces them. `app` and `app.cmd` stay as thin wrappers over `uv run app`.
- `scripts/check`, `scripts/check.py`: **new**. The one gate (lockfile, ruff lint and format, pyright, ty, unit tests with coverage) for git hooks, agents and CI.
- `src/app/`: fully annotated; `__version__` now reads the package metadata. `oslib.py` relaxes pyright for that one file because its Windows branches use APIs the Linux stubs lack. Formatting is `ruff format` (separate commit, no behaviour change).
- `tests/`: new `test_version.py` and a partial-settings test (coverage is 100% again); a few asserts split for ruff's PT018.
- `.github/workflows/unit.yml`, `integration.yml`: uv with cache; lint, format and types run once on Linux 3.13; weekly `uv audit`. `.github/dependabot.yml`: **new** (uv, npm, actions).
- README, AGENTS.md, test READMEs, docs: commands updated to uv and `scripts/check`.
- Not done yet: Dockerfile and systemd unit, copier conversion, release workflow (next phases).
