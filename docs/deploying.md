# Deploying

The app is one process: `uv run app serve` (FastAPI plus the built React app). Run it however you run long-lived services; [deploy/app.service](../deploy/app.service) is a systemd user-unit example.

1. Build the web app once per checkout: `cd web && npm ci && npm run build` (writes into `src/app/server/static/`).
2. `uv sync --locked --no-dev` installs the runtime dependencies only.
3. Choose a data folder **outside the checkout** and make it absolute: set `APP_DATA` in the service (as the example unit does) or run `uv run app set data_dir <folder>` once. Without either, data goes to `data/` inside the checkout and a fresh checkout loses it.
4. Start `uv run --locked --no-dev app serve --host 127.0.0.1 --port <port>`. In a service, give uv's full path: systemd does not search `~/.local/bin`.
5. Put a reverse proxy in front if you want TLS or a shared hostname. The app works under a path prefix (`/<prefix>/`) with no configuration: see "Reverse-proxy support" in [AGENTS.md](../AGENTS.md). Forward the prefix-stripped path to the app.
6. Check `GET /api/health`: it returns `{"ok": true, "version": ...}`.

## Keep the service and the repo in step

A service file that names a launch command can go stale when the repo is restructured, and the failure only shows as a restart loop. So:

- Start the app only through the `app` console script (`uv run app serve`), never through a path to a source file.
- Change the unit in the same change as any rename of the package, the command or the port.
- After a restart, a port that answers is not proof the right app is running: compare `/api/health`'s `version` with `pyproject.toml`.
- Once step 3 is done, data lives outside the checkout, so redeploying never touches it.
