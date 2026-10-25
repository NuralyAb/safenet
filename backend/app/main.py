import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.startup import run_startup

_log = logging.getLogger("afm")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        run_startup()
    except Exception as exc:  # noqa: BLE001
        # Fail-fast in production (a missing store is a real problem); tolerate in dev.
        if settings.app_env == "production":
            raise
        _log.warning("startup init skipped (dev): %s", exc)
    yield


app = FastAPI(
    title="SafeNet KZ — признаки незаконных схем в соцсетях",
    version="0.1.0",
    description="On-prem AI platform for fraud-network investigation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
