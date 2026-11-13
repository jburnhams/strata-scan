"""The application server: `./app serve` starts the FastAPI backend and serves the built React app.

    ./app serve [--host 127.0.0.1] [--port 8360]

API (JSON): GET /api/health; GET /api/system; GET /api/settings; PUT /api/settings {data_dir?, greeting?} (health and settings come from strata_python.web); GET /api/hello?name=&greeting=;
GET /api/messages; GET /api/messages/page?after=&limit=; POST /api/messages {name, greeting?}; DELETE /api/messages; DELETE /api/messages/{id}.
Every other path serves the web app (`src/app/server/static/index.html` when built with `cd web && npm run build`, else the plain stand-in `landing.html`),
so a reload or a shared link to /settings?tab=appearance opens that screen: the app routes in the browser (React Router)."""

import os
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from strata_python import web

from app import __version__, greet, settings, system

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
LANDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing.html")


class MessageIn(BaseModel):
    name: str = "World"
    greeting: str | None = None


def create_app() -> FastAPI:
    # health, settings and (last) the web app's page routes come from the shared library; the routes between are this app's own
    app = web.base_app("python-app-template", __version__, settings.SETTINGS)

    def guard(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
        try:
            return fn(*a, **kw)
        except greet.GreetingError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/system")
    def get_system():
        return system.status()

    @app.get("/api/hello")
    def get_hello(name: str = "World", greeting: str | None = None):
        return guard(greet.format_greeting, name, greeting)

    @app.get("/api/messages")
    def get_messages():
        return greet.list_messages()

    @app.get("/api/messages/page")
    def get_messages_page(after: int | None = None, limit: int = Query(20, ge=1, le=200)):
        return greet.page_messages(after, limit)

    @app.post("/api/messages")
    def post_message(b: MessageIn):
        return guard(greet.add_message, b.name, b.greeting)

    @app.delete("/api/messages")
    def delete_messages():
        return greet.clear_messages()

    @app.delete("/api/messages/{message_id}")
    def delete_message(message_id: int):
        removed = greet.remove_message(message_id)
        if removed is None:
            raise HTTPException(404, f"there is no greeting {message_id}")
        return removed

    web.add_web(app, STATIC, LANDING)
    return app


def main(argv: Sequence[str] | None = None) -> None:
    web.serve(create_app(), argv, default_port=8360, banner=f"data folder: {settings.data_dir()}")
