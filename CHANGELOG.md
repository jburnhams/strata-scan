# Changelog

Newest first, grouped by day. One entry per change, in the same commit or PR as the change.

## 2026-11-14

**Correct every text page's OCR with a vision-language model (branch `claude/project-thread-0n1ijc`)**
Jonathan asked for evals of the trickier pages, before and after OCR. On strata-models' ocr-pages eval (10 hard pages of both books, typed out by hand), Tesseract alone got 5.1 % of characters wrong, the best page cleaning 3.1 %, and Tesseract then qwen3.5-9b-vl correcting its text against the page 0.3 % (small capitals: "Puxcr", "Jupy" became PUNCH, JUDY), at about 18 s of GPU time a page. He chose to correct every text page.

- `pipeline.py`: after the OCR, a text page's text (noise lines already dropped) goes with its picture to strata-models' `vision-language` role (`models_correct`: preset `ocr-correct-v1`, temperature 0), and the page's text is the answer; `ocr["corrected"]` keeps `{model, text}` or `{model, error}`. Tesseract's lines and boxes stay, so the searchable PDF and figure finding are as before. A failed correction, or one far shorter or longer than its text (`plausible`), keeps Tesseract's text. Covers, pictures, blanks and typed pages are not sent; the kind is now guessed before the correction so a picture page is never sent. `Runner(correct=...)` stands in for the service in tests.
- `settings.py`: `correct` (STRATASCAN_CORRECT), the model key (default `qwen3.5-9b-vl`) or `off`.
- `tests/unit/test_pipeline.py`: corrections replace text pages' text and keep both; typed pages, pictures and covers are not sent; a failed or implausible correction keeps the OCR text; `off`. `tests/conftest.py`: the shared runner has no correction. `tests/utils/models_service.py`: the stand-in answers `vision-language` correction jobs; `tests/integration/test_cli.py`: each text page is sent for correction with its picture.
- README, `docs/overview.md`, `docs/progress.md`: the correction pass and its numbers.

## 2026-11-13

**Stop committing the web build (branch `claude/project-thread-0n1ijc`)**
Jonathan asked about the static assets folder: the built web app had been committed, because `.gitignore` still named the template's `src/app/server/static/` after the package rename.

- `.gitignore`: ignores `src/stratascan/server/static/` (what `npm run build` writes and `strata-scan serve` serves); the 18 built files are removed from git. Deploying builds them (`docs/deploying.md`, step 1).

**Review fixes: hand work, one-page tasks and failed reads (branch `claude/project-thread-0n1ijc`)**
Three findings from the automated review on #5, each confirmed by a test that failed before the fix.

- `src/stratascan/pipeline.py`: detect leaves a scan alone when any of its pages has a person's work (a cut, typed text, or a hand-drawn picture), not only a hand cut: re-detecting deleted the pages and their typed text and pictures with them. A task for chosen pages follows their scans through detect, which gives the new pages new ids (a following `read` found none). The book's error is cleared once per task, so a successful export no longer hides a read that failed.
- `tests/unit/test_pipeline.py`: a test for each.

**strata-scan: the web app, and blank pages kept whole (branch `claude/project-thread-0n1ijc`)**
The second half of the same request: the screens to look at a book, correct a page's cut, text and pictures, and make the files. Running the 1874 book through the API showed blank pages with no scanner bed cropped to a patch, so the page finder changed too.

- `web/src/api.ts`: the books/pages/scans/figures endpoints and their types, the geometry helpers the cut editor shares with the server (`turnedSize`, `turnCrop`, `wrapAngle`) and the sentences (`describeBook`, `pageName`).
- `web/src/screens/BooksScreen.tsx`, `BookScreen.tsx`, `PageScreen.tsx`: **new**; the shelf (add by upload or by path), a book (its work as a `useJob`, pages, pictures, files) and a page (cut: turn, crop, split or join a spread; text: unsure lines, kind, label; pictures: draw, remove). `Layout.tsx`, `routes.tsx`, `SystemScreen.tsx` (whether strata-models can read), `SettingsScreen.tsx` (data folder, resolution, pages at once), `NotFoundScreen.tsx`. `GreetingsScreen.tsx`, `LogScreen.tsx` and their tests, stories and baselines: removed.
- `web/src/mocks/fixtures.ts`, `handlers.ts`, `images.ts` (**new**: three page previews from the 1874 book, public domain): the two books as sample data, every endpoint and each failure state.
- `web/tests/integration/{Books,Book,Page}Screen.test.tsx` **new**; `App`, `Settings`, `System` tests and `tests/unit/logic.test.ts` rewritten. 65 tests, 100% on every coverage metric.
- `web/stories/{books,book,page}.stories.tsx` **new**, `system.stories.tsx`: NoReader. `web/strata-visual.config.ts`: books, book, page, system and settings routes; `web/tests/visual/baselines/`: all new (greetings and log removed).
- `web/vite.config.ts`: a function of the mode; `--mode visual` (`build:visual` in `package.json`) adds `<base href="/">`, because the visual runner serves the build without the server's `<base>` and a nested route (`/books/1`) otherwise asks for `/books/assets/...`. `web/vitest.config.ts` calls it for the test mode. Bundle size comment corrected (940 kB).
- `src/stratascan/geometry.py`: `_page_mask` takes the whole scan as the page when Otsu's two classes are closer than `BED_CONTRAST` (30): a scan of paper only. `tests/unit/test_geometry.py`: a blank page with no bed stays whole.

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
