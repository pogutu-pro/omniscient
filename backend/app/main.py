from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import academics, admin, auth, chat, complaints, files, housing, past_papers
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import enforce_default_rate_limit

settings = get_settings()
configure_logging(settings.app_env)
logger = get_logger(component="main")

app = FastAPI(
    title="Omniscient API",
    description="Smart campus assistant backend for Dedan Kimathi University of Technology (DeKUT) students.",
    version="0.1.0",
    dependencies=[Depends(enforce_default_rate_limit)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.error("unhandled_exception", path=request.url.path, correlation_id=correlation_id, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again.", "request_id": correlation_id},
    )


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(housing.router)
app.include_router(academics.router)
app.include_router(past_papers.router)
app.include_router(complaints.router)
app.include_router(files.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env, "llm_provider": settings.llm_provider, "rumia_db_mode": settings.rumia_db_mode}
