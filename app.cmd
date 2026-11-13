@echo off
rem Launcher for Windows: runs the app CLI in the uv-managed project environment (same as `uv run app`).
uv run --project "%~dp0." app %*
