"""FastAPI app for the Options Skill Pack."""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from slowapi.errors import RateLimitExceeded

from app.auth import auth_middleware, security_headers, _APP_API_KEY, _COOKIE_NAME, _make_session_token
from app.config import limiter
from app.chat import router as chat_router
from app.analyze import router as analyze_router
from app.portfolio import router as portfolio_router

logger = logging.getLogger("options_skill_pack")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Options Skill Pack")

# ── Unauthenticated exposure warning ──────────────────────────────────────
# If APP_API_KEY is unset AND the server is not bound to loopback, warn
# loudly. We don't hard-fail because Docker binds 0.0.0.0 by design.
if not _APP_API_KEY:
    _host = os.environ.get("HOST", "").strip()
    _loopback = _host in ("", "127.0.0.1", "localhost", "::1")
    if not _loopback and os.environ.get("ALLOW_NO_AUTH", "").lower() not in ("1", "true"):
        logger.warning(
            "SECURITY: APP_API_KEY is not set and HOST=%s is not loopback. "
            "The app is exposed without authentication. Set APP_API_KEY or "
            "ALLOW_NO_AUTH=1 to silence this warning.", _host or "unset",
        )

# ── Rate limiting ──────────────────────────────────────────────────────────

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "Rate limit exceeded. Please slow down."})


# ── CORS ────────────────────────────────────────────────────────────────────

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["content-type", "authorization"],
)

# ── Middleware ──────────────────────────────────────────────────────────────

app.middleware("http")(security_headers)
app.middleware("http")(auth_middleware)

# ── Routers ────────────────────────────────────────────────────────────────

app.include_router(chat_router)
app.include_router(analyze_router)
app.include_router(portfolio_router)


# ── Health check (unauthenticated) ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Static files ─────────────────────────────────────────────────────────────

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        response = FileResponse(os.path.join(static_dir, "index.html"))
        if _APP_API_KEY:
            response.set_cookie(
                _COOKIE_NAME, _make_session_token(),
                httponly=True, samesite="strict",
                secure=os.environ.get("SECURE_COOKIES", "").lower() in ("1", "true"),
            )
        return response
