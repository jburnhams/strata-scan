# python-app-template

A full-stack Python + React project template extracted from [strata-360](https://github.com/jburnhams/strata-360) and [strata-stills](https://github.com/jburnhams/strata-stills). Includes a FastAPI backend and CLI (`src/app/`), a React 19 + TypeScript frontend (`web/`) built on [strata-react](https://github.com/jburnhams/strata-react) that builds directly into the Python package, hermetic unit and integration test suites (uv run pytest + hypothesis on Python, Vitest + Testing Library + MSW on web), Storybook, screenshot tests in Chromium (`strata-visual`), ratcheting coverage gates, and multi-OS GitHub Actions CI.

The web app is meant to be read as well as run: each screen in `web/src/screens/` opens with the question it answers and the strata-react patterns it shows (loading, empty and error states; undoable removal; bulk selection; a cursor-paged log; a polled status page; settings with tabs in the URL; light and dark).

## Quick start

```bash
uv sync                              # creates .venv from uv.lock (install uv: https://docs.astral.sh/uv/)
uv run app doctor                         # check the environment
uv run app hello World                    # CLI hello world
uv run app serve                          # starts the FastAPI + React app on http://127.0.0.1:8360/
```

For hot-reload frontend development, run `./app serve` in one terminal and `cd web && npm run dev` in another (Vite proxies `/api` to `127.0.0.1:8360`).

## Using this template for a new project

1. Create a new repository from `python-app-template` on GitHub (or clone it).
2. Rename `src/app` and the `./app` / `app.cmd` launchers if you want a project-specific package name, and update `pyproject.toml` (`source = ["src/<pkg>"]`), `web/vite.config.ts` (`outDir`), and the settings prefix (`Settings("app", ...)`, `APP_DATA`) in `src/<pkg>/settings.py` and `strata_env_prefix` in `pyproject.toml`.
3. Replace the sample greeting module (`src/app/greet.py`) and screens (`web/src/screens/`) with your own, keeping the shape: one question per screen, every read through `useLoad`/`DataView`, mock handlers in `web/src/mocks/` for every endpoint.
4. Give the app its own look: regenerate `web/src/styles/theme.generated.css` with ux-research's `palette.mjs` from seeds that come from your subject, then re-solve the status roles and faces in `theme.css` (the header of each file has the command and the checks).
5. Rewrite the visual baselines once the screens are yours: `cd web && npm run test:visual:update`, look at every PNG, commit them.

## Documentation

| Document | What it is |
|---|---|
| [docs/overview.md](docs/overview.md) | The design brief: goals, architecture, layout. |
| [docs/implementation-plan.md](docs/implementation-plan.md) | Milestones and what to build next, in order. |
| [docs/progress.md](docs/progress.md) | The log of what was tried, measured and decided. |
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

The web app needs Node 26 (`.nvmrc`). The visual suite needs the Chromium of the pinned Playwright: `cd web && npx playwright install chromium`. Write baselines on Linux in that Chromium (as CI does); look at the diffs in `web/tests/visual/output/` before accepting any.

See [tests/README.md](tests/README.md) and [web/tests/README.md](web/tests/README.md) for the test layout, hermetic fixtures, and file-ownership conventions.
