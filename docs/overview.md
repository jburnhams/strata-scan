# Design brief

## 1. Goal

Provide a clean, minimal starting point for full-stack local-first Python + React applications with the exact build, test, coverage-gate and multi-OS CI setup proven in `strata-360` and `strata-stills`.

## 2. Architecture

- **Python CLI and HTTP server (`src/app/`)**:
  - `cli.py`: command-line interface (`doctor`, `hello`, `messages`, `set`, `serve`), invoked as `uv run app` (the `app` console script from `pyproject.toml`; `./app` and `app.cmd` wrap it).
  - `server/app.py`: FastAPI application serving JSON endpoints under `/api/*` and the built React single-page app at `/` (falling back to `server/landing.html` when `web/` has not been built yet).
  - `settings.py`: persistent user configuration in `~/.app/settings.json` (`APP_HOME` override) with atomic file writes.
  - `oslib.py`: cross-platform primitives (file locks, process liveness, process tree termination, priority, CLI command builder) isolating POSIX vs Windows differences in one place.
  - `greet.py`: minimal "Hello, world!" domain module with pure formatting functions and a file-locked JSON message log in the configured data directory (ids never reused, cursor paging, removal of one).
  - `system.py`: the snapshot the System screen shows (versions, data folder size, disk usage).
- **React frontend (`web/`)**, built on [strata-react](https://github.com/jburnhams/strata-react) (components, UX patterns, the token contract and the testing and screenshot tooling):
  - React 19, TypeScript, Vite 8, Tailwind CSS v4 with Strata's token contract (Tailwind's stock colours, sizes and radii do not compile), a palette generated from the subject (`web/src/styles/`), bundled faces.
  - React Router with real paths (`web/src/routes.tsx`, one tree shared by the app, the tests and the stories); URL state for sort and tabs. The server answers every page path with the app and a relative `<base>`, so one build works at `/` or behind a reverse proxy at `/<subpath>/` (`with_base` in `server/app.py`, `BASE`/`withBase()` in `web/src/api.ts`).
  - Server data through TanStack Query (`useLoad`, `useInfiniteLoad`, `fetchJson`), shown through `DataView`/`InfiniteList` so loading, empty and error states cannot be left out.
  - MSW handlers for every endpoint (`web/src/mocks/`) serve the jsdom tests, Storybook and the visual suite.
  - `npm run build` outputs directly to `src/app/server/static/`.

## 3. Principles

- **Hermetic tests by default**: every test run gets an isolated home and data directory outside `tmp_path`, stripped environment overrides, and a socket guard that blocks outbound network calls.
- **Two-tier test suites**: fast unit tests (`tests/unit/`, `web/tests/unit/`) and end-to-end integration tests (`tests/integration/`, `web/tests/integration/`), with clear file ownership so parallel agent branches never conflict.
- **Ratcheting coverage floors**: Python unit coverage (`fail_under` in `pyproject.toml`) and web combined coverage (`web/coverage-floor.json`) only ratchet up.
