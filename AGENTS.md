# Repository Guidelines

This file is for people and coding agents (`CLAUDE.md` imports it). It is the basis for the same file in every app made from [python-app-template](https://github.com/jburnhams/python-app-template): when you start an app from the template, keep the sections, replace the descriptions of the sample code with your app's, and keep what is true for every app unchanged so the template can be updated into it later.

## What this is

A Python backend (FastAPI + CLI) and a React frontend built on [strata-react](https://github.com/jburnhams/strata-react) (TypeScript + Vite + Tailwind CSS v4), extracted from `strata-360` and `strata-stills`. Hermetic unit and integration test suites, Storybook, screenshot tests, coverage ratchets and multi-OS GitHub Actions CI. The sample app (greetings, a log, settings, a status page) exists to show the patterns; replace it, keep the shape.

## Rules for every change

1. **Run `scripts/check` before every commit** (`--fast` skips the tests, `--fix` applies ruff). CI runs the same steps. Never skip, disable or quarantine a test or a check to get green.
2. **Keep the docs and the changelog in the same commit as the change**: add an entry to `CHANGELOG.md` (newest day first; a bold one-line title, what was asked, then bullets naming each file touched and what changed; say **new** for new files, and call out corrections to earlier claims), and update the README, this file and `docs/` where they stop being true.
3. **Write the why**: dense code with comments that say why, not what. Facts, commands, paths and decisions; link instead of repeating what another doc or upstream page already says.
4. **No secrets, no machine-specific details** in this repo. Say where a secret lives (an environment variable name, a password manager), never its value. Hostnames, addresses, user names, local paths and the owner's infrastructure belong in the owner's private docs, not here: examples use placeholders (`/home/ada/...`, `<port>`).
5. **Types are not optional**: everything in `src/` is fully annotated and passes `pyright` (strict) and `ty`; a new file is strict from its first commit. Style is `ruff format` at line length 120, not by hand.
6. **Tests come with the change**: unit tests for logic, integration tests for the CLI and HTTP API, web tests and stories for screens. Coverage floors only ratchet up.
7. **Say what you ran**: in the PR or the final message, list the commands you ran and their results, and name what you could not run.

## Layout and conventions

- Shared server code is the [strata-python](https://github.com/jburnhams/strata-python) library (read its `AGENTS.md`): `oslib`, the `Settings` class, `web.base_app`/`add_web`/`with_base`/`serve`, the `doctor`/`set`/`serve` CLI commands, the pytest plugin and the `strata-check` gate. Do not copy those modules into the app; if the library lacks something every app needs, change it there. This repo only declares its settings (`settings.py`), its own routes (`server/app.py`) and its own commands (`cli.py`).
- Python application code lives in `src/app/` (the package name is changed per app, see the README); the React web app lives in `web/src/` and builds into `src/app/server/static/`, which `app serve` serves at every non-API path.
- The web app follows strata-react's rules (its `CLAUDE.md`, "Building an app on Strata"): only Strata components and theme roles (no raw palette colours, arbitrary values or `dark:` overrides), every remote read `useLoad`/`useInfiniteLoad` → `DataView`/`InfiniteList` with skeleton and empty state, one filled button per view at a time (the `BulkBar` action takes it while rows are chosen), reversible removals through `useUndoable`, URL state for sort/tab, numbers and dates through `format`. Each screen in `web/src/screens/` opens with its one question. Something Strata lacks is raised as an issue on strata-react, not hand-built here.
- Cross-platform (Linux, macOS, Windows): OS differences (file locks, process liveness and termination, priority, how to start the CLI) live in `strata_python.oslib`; do not import `fcntl` or call `os.kill(pid, 0)` elsewhere (on Windows that terminates the process).
- Reverse-proxy support: the server gives every page a relative `<base href>` back to its root (`with_base` in `server/app.py`), the web build uses relative asset paths (`base: './'` in `vite.config.ts`), and `BASE` comes from the page's base URL (`web/src/api.ts`); it is React Router's `basename`. Any URL the app builds for `fetch`, `<img>` or an external link must go through `withBase`; in-app links are router paths.
- Docs live in `docs/`: `overview.md` (design brief), `implementation-plan.md` (milestones and next steps), `progress.md` (log of findings and decisions), `deploying.md` (running it as a service; keep it generic), `prompts/` (unattended agent prompts for backend unit, integration and web tests).

## Python tooling (uv)

- `uv sync` builds `.venv` from the committed `uv.lock`; `uv run <cmd>` runs inside it; `uv add <pkg>` / `uv add --group dev <pkg>` change dependencies (commit `pyproject.toml` and `uv.lock` together). Version, dependencies, the `app` entry point and every tool's configuration are in `pyproject.toml`; the version lives only there (`app.__version__` reads it back). `./app` and `app.cmd` are thin wrappers for `uv run app`.
- `scripts/check` is `uv run --locked strata-check` (from strata-python): `uv lock --check`, `ruff check`, `ruff format --check`, `pyright` and `ty`, then the unit tests with coverage. Options such as the checked paths are in `[tool.strata-check]` in `pyproject.toml`.
- strata-python is a git dependency that tracks its `main` branch (`[tool.uv.sources]`, no tag); `uv.lock` pins the commit. `.github/workflows/upgrade-strata-python.yml` runs `uv lock --upgrade-package strata-python` weekly, runs the gate and integration tests on the result and opens a PR. Do the same by hand to pick up a library change at once.
- `uv run pytest tests/unit --cov` runs the unit suite with coverage (random order via pytest-randomly; `-n auto` runs in parallel; `diff-cover` checks the lines a change touches). `uv run pytest tests/integration -n auto` runs the integration suite.
- `uv run app doctor` checks the environment; `uv run app hello [name]` prints and records a greeting; `uv run app serve` runs the web server on port 8360.
- Python coverage is calculated from the unit suite only (`fail_under` in `pyproject.toml`).
- Style: pytest style tests (`def test_...` with `assert`; use `monkeypatch`/`tmp_path` instead of patching globals by hand).

## Testing policy

Prefer real code over mocks. A test that runs the real thing finds the bugs that matter; a mock only proves the code agrees with the test.

- **Real by default**: real HTTP requests (against a real local server: the `http_server` fixture from the strata-python plugin, or its `live_app` fixture to run the app itself on a loopback port), real embedded databases (SQLite, or the Postgres service container, via the database project's `db_session` fixtures; see Database), real files in `tmp_path`, real subprocesses. In the web app that means MSW answering real `fetch` calls, never a stubbed `fetch` or a mocked module.
- **Mocks and fakes are the exception**: use one only for a true external (a paid or remote service, hardware, the clock) and only in quick unit tests that cover many cases where speed is the point. Never mock your own modules or the database. Even then, keep one test of the same path against the real thing.
- **Install what the tests need**: CI runners can have software installed. If code calls `ffmpeg`, install it (locally and in the workflow) and run it; do not mock it or skip when it is missing. Add the install to the workflow and say so in the README.
- **No silent skips, no swallowed errors**: a test must not pass or skip because something was missing or an exception was caught. `pytest.importorskip` is banned (ruff). A test is skipped only deliberately: a marker or `skipif` with a **reason** and an explicit switch, for example a 12 GB model that is too large for CI is `@pytest.mark.skipif(not os.environ.get("RUN_LARGE_MODEL"), reason="needs the 12 GB model; set RUN_LARGE_MODEL=1")` and runs on the machine that has it. Skips show in the summary (`-ra`); any new skip is mentioned in the PR.
- **Where tests need a lot of machine** (GPU, large models), mark them (`slow`, `gpu`), run them where that machine exists, and keep the marker documented in `tests/README.md`.

## Python tests

- Tests live under `tests/`, grouped by type:
  - `tests/unit/`: fast, isolated tests of pure logic and mocked boundaries (synthetic data, fakes). No external processes or network.
  - `tests/integration/`: end-to-end tests that run the CLI (in-process and as a subprocess) and the FastAPI HTTP API over real on-disk state.
  - `tests/utils/`: shared helpers (`fakes.py`, last-resort doubles for the outside world). The strata-python pytest plugin (configured by `strata_env_prefix` and `strata_tuning_vars` in `pyproject.toml`) makes every suite hermetic (isolated home and data dir, no network) and provides the `http_server` and `live_app` fixtures; `tests/conftest.py` holds the rest.
- Read `tests/README.md` before writing any Python test: fixtures, conventions, file-ownership rules and the per-module coverage ledger.

## Web

- Web tests live in `web/tests/{unit,integration,utils}` (vitest; unit runs in node, integration in jsdom through `renderRoutes` from `strata-react/testing`). Backend calls are answered by msw from `web/src/mocks/handlers.ts` (every endpoint the app calls needs a handler there; the same handlers serve Storybook and the visual suite); read `web/tests/README.md` before writing any. Stories live in `web/stories/`; visual baselines in `web/tests/visual/baselines/`.
- Commands, from `web/`: `npm install`, `npm run dev` (proxies `/api` to `app serve` on 8360), `npm run build` (writes into `src/app/server/static/`), `npm run typecheck`, `npm run test:unit` (node), `npm run test:integration` (jsdom + msw), `npm run test:coverage:gate` (unit + integration together, what CI gates on: floors in `web/coverage-floor.json`, read by `web/vitest.gate.config.ts`), `npm run test:coverage` (unit only, informational), `npm run test:coverage:all` (unit + integration, no gate), `npm run storybook`, `npm run build-storybook`, `npm run test:visual` (builds the app and Storybook, then `strata-visual` compares every story and route state, light and dark, with the baselines), `npm run test:visual:update` (look at the diffs in `tests/visual/output/` first, say in the PR which baselines changed and why). Node 26 (`.nvmrc`). The web floors only ratchet up.

## Database

The template ships no database (the sample keeps JSON files in the data folder). When an app needs one, use the shared database project, [`jburnhams/database`](https://github.com/jburnhams/database) (library `omarchy_db`), not an ad-hoc `sqlite3` file or a database of its own. Follow its [adoption guide](https://github.com/jburnhams/database/blob/main/docs/ADOPTING.md) and do not restate it here; the rules that matter to an agent:

- One shared database, one schema per app. Never one database per app: Postgres cannot join across databases.
- The app's models (typed SQLAlchemy records from `omarchy_db.make_base()`) and its Alembic migrations live in this repo; the library and `dbtool` come from the database project. Add it with a git source in `pyproject.toml` (`[tool.uv.sources]`, see the guide) so CI can resolve it, and commit `uv.lock`.
- Models stay portable (generic SQLAlchemy types, a `server_default` on new NOT NULL columns) unless the app really needs Postgres features; then set `engine = "postgres"` in `[tool.omarchy-db]`.
- Every model change comes with a reviewed migration (`dbtool revision -m "..."`; autogenerate sees a rename as drop + add). CI runs `dbtool check`; tests use the plugin's `db_session` fixtures, never a mocked connection. If CI needs Postgres (pgvector, say), run it as a service container.
- Run migrations at app start (`Project.load(__file__).upgrade(engine)`) or with `dbtool migrate`.
- Connection settings come from the environment (see the guide); never put a URL with credentials in the repo.
- For data that is personal (photos, people, children) keep it out of git and behind a login.
- A worked example in this family: [bright-horizons](https://github.com/jburnhams/bright-horizons) (`src/bright_horizons/db/`, `migrations/`).
- If the database project lacks something an app needs, raise it as an issue there instead of working around it here.

## CI

`.github/workflows/unit.yml` (`strata-check --fast` once, then unit tests with coverage on Linux Python 3.11-3.13, macOS and Windows; web typecheck, coverage gate, build, Storybook build; visual regression) and `integration.yml` (integration tests on Linux, macOS and Windows, web component tests, a weekly dependency audit, weekly and on demand). `update-visual-baselines.yml` (manual) rewrites the visual baselines on the CI runner for a branch, which is how a Dependabot browser or icon bump gets new baselines. `.github/dependabot.yml` keeps uv, npm and Actions dependencies current. CI installs with `uv sync --locked`, so a stale lockfile fails the build.

## Before you say it is done

`scripts/check` passes, the integration suite passes, the web checks you touched pass (`typecheck`, `test:coverage:gate`, `test:visual` for any UI change), the changelog has its entry, and the docs match the code. Report the commands and their results.
