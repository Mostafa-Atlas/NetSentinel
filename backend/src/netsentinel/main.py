import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from netsentinel import (
    alerts,
    auth,
    check_rules,
    identity,
    inventory,
    monitoring,
    profiles,
    scans,
    scopes,
    views,
)
from netsentinel.db import make_engine
from netsentinel.discovery import DefaultProbeRunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    scans.recover_interrupted(app)
    app.state.scan_queue = asyncio.Queue(maxsize=4)
    worker = asyncio.create_task(scans.scan_worker(app))
    scheduler = asyncio.create_task(monitoring.scheduler_loop(app))
    try:
        yield
    finally:
        worker.cancel()
        scheduler.cancel()
        await asyncio.gather(worker, scheduler, return_exceptions=True)


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="NetSentinel", version="0.1.0", lifespan=lifespan)
    engine = make_engine(
        database_url or os.getenv("NETSENTINEL_DATABASE_URL") or "sqlite:///./netsentinel.db"
    )
    app.state.engine = engine
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.login_attempts = {}
    app.state.prober = DefaultProbeRunner()

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "http_error", "message": str(exc.detail)}
        )
        return JSONResponse(
            status_code=exc.status_code, content={**detail, "request_id": request.state.request_id}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Invalid request",
                "details": [
                    {"loc": [str(x) for x in item["loc"]], "message": item["msg"]}
                    for item in exc.errors()
                ],
                "request_id": request.state.request_id,
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(scopes.router)
    app.include_router(profiles.router)
    app.include_router(scans.router)
    app.include_router(inventory.router)
    app.include_router(identity.router)
    app.include_router(check_rules.devices_router)
    app.include_router(check_rules.rules_router)
    app.include_router(monitoring.router)
    app.include_router(views.router)
    app.include_router(alerts.alerts_router)
    app.include_router(alerts.events_router)

    static_dir = Path(os.getenv("NETSENTINEL_STATIC_DIR", ""))
    if os.getenv("NETSENTINEL_STATIC_DIR") and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


app = create_app()
