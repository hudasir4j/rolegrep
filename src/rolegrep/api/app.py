"""FastAPI app: list postings / watchlist, trigger a monitor pass."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rolegrep.config import PROJECT_ROOT
from rolegrep.db.repository import (
    add_watched_url,
    deactivate_watched_url,
    list_monitor_runs,
    list_postings,
    list_watched_urls,
    monitor_run_to_dict,
    posting_to_dict,
    watched_url_to_dict,
)
from rolegrep.db.session import init_db, session_scope


class WatchUrlCreate(BaseModel):
    url: str = Field(min_length=8)
    label: str | None = None


class MonitorTriggerResponse(BaseModel):
    status: str
    message: str


def _run_monitor_background(*, limit: int | None) -> None:
    from rolegrep.monitor.runner import run_monitor_once

    run_monitor_once(limit=limit)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app(*, serve_frontend: bool = True) -> FastAPI:
    app = FastAPI(
        title="Rolegrep",
        description="Internship monitor API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/postings")
    def get_postings(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        relevant_only: bool = False,
        include_duplicates: bool = False,
    ) -> dict[str, Any]:
        with session_scope() as session:
            rows = list_postings(
                session,
                limit=limit,
                offset=offset,
                relevant_only=relevant_only,
                include_duplicates=include_duplicates,
            )
            return {
                "count": len(rows),
                "postings": [posting_to_dict(row) for row in rows],
            }

    @app.get("/api/urls")
    def get_urls(active_only: bool = False) -> dict[str, Any]:
        with session_scope() as session:
            rows = list_watched_urls(session, active_only=active_only)
            return {
                "count": len(rows),
                "urls": [watched_url_to_dict(row) for row in rows],
            }

    @app.post("/api/urls", status_code=201)
    def create_url(body: WatchUrlCreate) -> dict[str, Any]:
        with session_scope() as session:
            row = add_watched_url(session, body.url.strip(), label=body.label)
            return watched_url_to_dict(row)

    @app.delete("/api/urls/{url_id}")
    def delete_url(url_id: int) -> dict[str, Any]:
        with session_scope() as session:
            row = deactivate_watched_url(session, url_id)
            if row is None:
                raise HTTPException(status_code=404, detail="URL not found")
            return watched_url_to_dict(row)

    @app.get("/api/runs")
    def get_runs(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        with session_scope() as session:
            rows = list_monitor_runs(session, limit=limit)
            return {
                "count": len(rows),
                "runs": [monitor_run_to_dict(row) for row in rows],
            }

    @app.post("/api/monitor/run", response_model=MonitorTriggerResponse)
    def trigger_monitor(
        background_tasks: BackgroundTasks,
        limit: int | None = Query(None, ge=1, le=100),
    ) -> MonitorTriggerResponse:
        """Kick off a monitor pass in the background (needs API keys in env)."""
        background_tasks.add_task(_run_monitor_background, limit=limit)
        return MonitorTriggerResponse(
            status="started",
            message="Monitor pass started in the background",
        )

    web_dist = PROJECT_ROOT / "web" / "dist"
    if serve_frontend and web_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(web_dist / "index.html")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            # Don't swallow API routes (already registered above)
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = web_dist / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web_dist / "index.html")

    return app


app = create_app()
