# strata-scan

Scanned books in, pages and text out. Give it a PDF (an Internet Archive scan, say) or a folder of photographs and it:

1. **imports** the scans, drawing each PDF page at the resolution of the scan inside it;
2. **finds the pages**: the page outline in each scan, levelled (to the paper's edge, then to the lines of type), cropped, a two-page spread split at its gutter; covers and dark scans are kept whole;
3. **reads** each page with OCR (the `ocr` role of [strata-models](https://github.com/jburnhams/strata-models): Tesseract today) and cuts out the **pictures** (engravings, diagrams) as what is ink but not text; pages are marked text, picture, cover or blank, and the running head becomes the page's label;
4. **exports** `book.md` (paragraphs rejoined, running heads dropped, pictures in place), `book.txt`, a searchable `book.pdf` and a `book.zip` with the pictures.

Every guess is a first draft a person corrects in the web app: turn or re-crop a page, split or join a spread, draw or remove a picture, type over the text. Corrections survive a re-run.

It is built on [strata-react](https://github.com/jburnhams/strata-react) (web), [strata-python](https://github.com/jburnhams/strata-python) (server plumbing) and the shared database (schema `stratascan`), from [python-app-template](https://github.com/jburnhams/python-app-template). [diary-study](https://github.com/jburnhams/diary-study) is the prior art.

## Quick start

```bash
uv sync                                         # .venv from uv.lock (install uv: https://docs.astral.sh/uv/)
uv run strata-scan doctor                       # check the environment
uv run strata-scan add ~/books/punch.pdf --title "Punch and Judy"   # import, find pages, read, export
uv run strata-scan books                        # every book and its state
uv run strata-scan run 1 read export            # run stages again (import, detect, read, export)
uv run strata-scan serve                        # the web app on http://127.0.0.1:8368/
```

Reading needs strata-models running with its `ocr` role (`STRATA_MODELS_URL`, default `http://127.0.0.1:8366`), which needs the `tesseract` command (Tesseract 5 and its `eng` data) on that machine. The records need a database: the shared one by default (see AGENTS.md, Database), or `STRATASCAN_DATABASE_URL=sqlite:////abs/path/scan.db` for a trial run (`uv run dbtool migrate --url ...` once). Pictures go in the data folder (`strata-scan set data_dir /abs/folder` or `STRATASCAN_DATA`). Settings: `max_dpi` (600: the most a PDF page is drawn at) and `workers` (4: pages worked on at once).

For hot-reload frontend development, run `./strata-scan serve` in one terminal and `cd web && npm run dev` in another (Vite proxies `/api` to `127.0.0.1:8368`).

## Documentation

| Document | What it is |
|---|---|
| [docs/overview.md](docs/overview.md) | The design brief: goals, architecture, layout. |
| [docs/implementation-plan.md](docs/implementation-plan.md) | Milestones and what to build next, in order. |
| [docs/progress.md](docs/progress.md) | The log of what was tried, measured and decided. |
| [docs/deploying.md](docs/deploying.md) | Running it as a service behind a reverse proxy. |
| [AGENTS.md](AGENTS.md) | Repository conventions and commands (for people and coding agents). |

## Tests

```bash
uv sync                                 # runtime + dev dependencies from uv.lock
uv run pytest tests/unit --cov                 # unit tests + coverage (CI gates on fail_under in pyproject.toml)
uv run pytest tests/integration -n auto        # CLI and HTTP API end-to-end
scripts/check                           # the whole gate (strata-check from strata-python): lockfile, ruff lint + format, pyright strict, ty, unit tests + coverage
cd web && npm run test:coverage:gate    # web unit + jsdom integration tests against coverage-floor.json
cd web && npm run storybook             # every screen in every server state, on :6006
cd web && npm run test:visual           # build the app and Storybook, then screenshot both light and dark against tests/visual/baselines/
```

The Python tests run the real `tesseract` (install Tesseract 5 with English data: `apt install tesseract-ocr`, `brew install tesseract`, `choco install tesseract`). The web app needs Node 26 (`.nvmrc`). The visual suite needs the Chromium of the pinned Playwright: `cd web && npx playwright install chromium`. Write baselines on Linux in that Chromium (as CI does); look at the diffs in `web/tests/visual/output/` before accepting any.

See [tests/README.md](tests/README.md) and [web/tests/README.md](web/tests/README.md) for the test layout, hermetic fixtures, and file-ownership conventions.
