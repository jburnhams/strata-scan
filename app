#!/bin/bash
# Launcher: runs the app CLI in the uv-managed project environment (same as `uv run app`).
exec uv run --project "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" app "$@"
