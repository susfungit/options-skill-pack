"""FastAPI app for the Options Skill Pack."""

import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from slowapi.errors import RateLimitExceeded

from app.auth import (
    auth_middleware, security_headers, is_authenticated, valid_api_key,
    set_session_cookie, _APP_API_KEY,
)
from app.config import limiter
from app.chat import router as chat_router
from app.analyze import router as analyze_router
from app.portfolio import router as portfolio_router
from app.trade_plans import router as trade_plans_router

logger = logging.getLogger("options_skill_pack")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Options Skill Pack")

# ── Fail closed on unauthenticated network exposure ────────────────────────
# If APP_API_KEY is unset AND the server is not provably bound to loopback,
# refuse to start. The bind host comes from uvicorn's `--host` argv (HOST env
# is a fallback) since Docker/uvicorn don't set HOST. Operators who knowingly
# run open (e.g. behind a loopback-only Docker publish) opt in via ALLOW_NO_AUTH.
def _detect_bind_host() -> str:
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--host" and i + 1 < len(argv):
            return argv[i + 1].strip()
        if arg.startswith("--host="):
            return arg.split("=", 1)[1].strip()
    return os.environ.get("HOST", "").strip()


if not _APP_API_KEY:
    _host = _detect_bind_host()
    _loopback = _host in ("", "127.0.0.1", "localhost", "::1")
    _allow_no_auth = os.environ.get("ALLOW_NO_AUTH", "").lower() in ("1", "true")
    if not _loopback and not _allow_no_auth:
        raise RuntimeError(
            f"SECURITY: APP_API_KEY is not set and bind host {_host!r} is not "
            "loopback. Refusing to start an unauthenticated, network-exposed "
            "server. Set APP_API_KEY to require auth, or ALLOW_NO_AUTH=1 to "
            "explicitly run without authentication (e.g. behind a loopback-only "
            "Docker port publish)."
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
app.include_router(trade_plans_router)


# ── Health check (unauthenticated) ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Auth (unauthenticated endpoints) ──────────────────────────────────────

@app.post("/api/login")
async def login(request: Request):
    """Exchange a valid API key (Authorization: Bearer …) for a session cookie."""
    if not _APP_API_KEY:
        # Auth disabled — nothing to log in to.
        return JSONResponse(status_code=400, content={"detail": "Authentication is not enabled"})
    bearer = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not valid_api_key(bearer):
        logger.warning("Login failure from %s", request.client.host if request.client else "unknown")
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
    response = JSONResponse(content={"status": "ok"})
    set_session_cookie(response)
    return response


@app.get("/api/auth/status")
async def auth_status(request: Request):
    """Report whether login is required and whether this request is authenticated."""
    return {"auth_required": bool(_APP_API_KEY), "authenticated": is_authenticated(request)}


# ── Static files ─────────────────────────────────────────────────────────────

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        # The shell is public; it grants no session. Clients obtain a session by
        # POSTing a valid key to /api/login.
        return FileResponse(os.path.join(static_dir, "index.html"))
