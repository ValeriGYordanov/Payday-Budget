"""FastAPI app factory. Production entry point: `python -m app` (see `__main__`)."""

import asyncio
import contextlib
import datetime as dt
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app import api_token, clock, config, discovery, migrate
from app.api.routes import router
from app.auth import AuthMiddleware
from app.db import make_engine, make_session_factory
from app.errors import ApiError
from app.events import Broadcaster
from app.scheduler import Scheduler, run_once

_LOGGER = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, field: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        body["field"] = field
    return JSONResponse(status_code=status, content=body)


async def _api_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    first = exc.errors()[0] if exc.errors() else {}
    loc = [str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path")]
    return _error(
        422, "validation_error", str(first.get("msg", "Invalid request")), ".".join(loc) or None
    )


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    code = "not_found" if exc.status_code == 404 else "http_error"
    return _error(exc.status_code, code, str(exc.detail))


async def _integrity_error(_request: Request, exc: Exception) -> JSONResponse:
    _LOGGER.warning("Integrity error: %s", exc)
    return _error(409, "conflict", "The change conflicts with existing data")


STATIC_DIR = Path(__file__).resolve().parent / "static"  # built by `frontend` (npm run build)
UI_MISSING_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Payday Budget</title></head>
<body><p>The UI has not been built. Run <code>npm run build</code> in <code>frontend/</code>.</p>
</body></html>
"""


def _mount_ui(app: FastAPI, static_dir: Path) -> None:
    """Serve the SPA: `index.html` at `/`, hashed bundles under `/assets` (§6.6)."""
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    def ui() -> Response:
        if not index.is_file():
            return HTMLResponse(UI_MISSING_PAGE, status_code=503)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app(
    data_dir: str | Path | None = None,
    *,
    today: Callable[[], dt.date] = clock.today,
    now: Callable[[], dt.datetime] | None = None,
    announce: Callable[[str], object] | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    base = Path(data_dir) if data_dir is not None else config.data_dir()
    engine = make_engine(str(config.db_path(base)))
    migrate.upgrade(engine)
    session_factory = make_session_factory(engine)
    token = api_token.load_or_create(base)
    broadcaster = Broadcaster()

    def job() -> None:
        run_once(session_factory, today)
        broadcaster.publish_threadsafe()

    scheduler = Scheduler(job=job, now=now or (lambda: dt.datetime.now(clock.local_zone())))
    announce = announce or (lambda t: discovery.send(t, config.PORT))

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        broadcaster.bind(asyncio.get_running_loop())
        await scheduler.run_job()  # R2: catch up on start, before serving requests
        tasks = [
            asyncio.create_task(scheduler.run_daily()),
            asyncio.create_task(asyncio.to_thread(announce, token)),  # §6.3
        ]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="Payday Budget",
        version="0.3.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.today = today
    app.state.token = token
    app.state.broadcaster = broadcaster
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.include_router(router)
    app.add_middleware(AuthMiddleware, token=token, broadcaster=broadcaster)

    _mount_ui(app, static_dir or STATIC_DIR)
    return app
