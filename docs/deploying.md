# Deploying

The app is one process: `uv run strata-scan serve` (FastAPI plus the built React app). Run it however you run long-lived services; [deploy/strata-scan.service](../deploy/strata-scan.service) is a systemd user-unit example and [deploy/strata-scan.caddy](../deploy/strata-scan.caddy) a Caddy snippet for a path prefix.

1. Build the web app once per checkout: `cd web && npm ci && npm run build` (writes into `src/stratascan/server/static/`).
2. `uv sync --locked --no-dev` installs the runtime dependencies only.
3. Choose a data folder **outside the checkout** and make it absolute: set `STRATASCAN_DATA` in the service (as the example unit does) or run `uv run strata-scan set data_dir <folder>` once. Without either, data goes to `data/` inside the checkout and a fresh checkout loses it.
4. Create the app's schema and role in the shared database (`dbtool new-app stratascan`, see the database project's adoption guide) and set `OMARCHY_DB_LIVE=1` in the service; the server migrates on start.
5. Run [strata-models](https://github.com/jburnhams/strata-models) where the app can reach it (`STRATA_MODELS_URL`), with the `tesseract` command and its English data installed on that machine: its `ocr` role reads the pages.
6. Start `uv run --locked --no-dev strata-scan serve --host 127.0.0.1 --port <port>`. In a service, give uv's full path: systemd does not search `~/.local/bin`.
7. Put a reverse proxy in front if you want TLS or a shared hostname. The app works under a path prefix (`/<prefix>/`) with no configuration: see "Reverse-proxy support" in [AGENTS.md](../AGENTS.md). Forward the prefix-stripped path to the app, and allow request bodies the size of a scanned book (uploads).
8. Check `GET /api/health` (`{"ok": true, "version": ...}`) and `GET /api/system` (`models.available` true: strata-models answers and has the `ocr` role).

## Keep the service and the repo in step

A service file that names a launch command can go stale when the repo is restructured, and the failure only shows as a restart loop. So:

- Start the app only through the `strata-scan` console script (`uv run strata-scan serve`), never through a path to a source file.
- Change the unit in the same change as any rename of the package, the command or the port.
- After a restart, a port that answers is not proof the right app is running: compare `/api/health`'s `version` with `pyproject.toml`.
- Once step 3 is done, data lives outside the checkout, so redeploying never touches it.
