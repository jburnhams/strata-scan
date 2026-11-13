# Implementation plan

- [x] **M0 scaffold**: repository layout, `uv sync` setup (replaced the earlier `setup_env` scripts on 2026-11-09), `./app` and `app.cmd` launchers, `oslib.py`, `settings.py`, `doctor` CLI command.
- [x] **M1 hello-world backend & CLI**: `greet.py` domain module, `hello` and `messages` CLI commands, FastAPI server (`server/app.py`) with `landing.html` fallback.
- [x] **M2 React web app**: Vite + React 19 + Tailwind CSS v4 frontend (`web/`), hash router (`route.ts`), reverse-proxy-safe API client (`api.ts`), greeting and settings pages.
- [x] **M3 test suites & CI**: hermetic pytest unit and integration suites, Vitest unit (node) and integration (jsdom + msw) suites, coverage gates, and GitHub Actions workflows (`unit.yml`, `integration.yml`).
- [x] **M4 web app on strata-react**: the frontend rebuilt on [strata-react](https://github.com/jburnhams/strata-react) as a worked example for new apps (Greetings, Log, System, Settings screens; React Router with real paths; TanStack Query through `useLoad`; a theme generated from the subject), with Storybook and `strata-visual` screenshot tests in CI. The API gained `GET /api/system`, `GET /api/messages/page` and `DELETE /api/messages/{id}`, and serves the app at every page path.
