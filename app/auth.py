"""API key auth, session cookies, and security headers."""

import hashlib
import hmac
import logging
import os
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("options_skill_pack")

_APP_API_KEY = os.environ.get("APP_API_KEY")
_SESSION_SECRET = secrets.token_hex(32)
_COOKIE_NAME = "osp_session"
_SESSION_TTL = int(os.environ.get("SESSION_TTL", 86400))  # 24 hours


def _make_session_token() -> str:
    """Create an HMAC-signed session token with expiry, tied to this server instance."""
    nonce = secrets.token_hex(16)
    issued = str(int(time.time()))
    payload = f"{nonce}.{issued}"
    sig = hmac.new(_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{issued}.{sig}"


def _valid_session_token(token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False
    nonce, issued, sig = parts
    try:
        if int(time.time()) - int(issued) > _SESSION_TTL:
            return False
    except ValueError:
        return False
    payload = f"{nonce}.{issued}"
    expected = hmac.new(_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def valid_api_key(bearer: str) -> bool:
    """Constant-time check of a bearer key against the configured APP_API_KEY."""
    if not _APP_API_KEY or not bearer:
        return False
    return hmac.compare_digest(bearer, _APP_API_KEY)


def is_authenticated(request: Request) -> bool:
    """True if auth is disabled, or the request carries a valid key/session."""
    if not _APP_API_KEY:
        return True
    bearer = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    cookie = request.cookies.get(_COOKIE_NAME, "")
    return valid_api_key(bearer) or _valid_session_token(cookie)


def set_session_cookie(response) -> None:
    """Attach a fresh signed session cookie to a response."""
    response.set_cookie(
        _COOKIE_NAME, _make_session_token(),
        httponly=True, samesite="strict", max_age=_SESSION_TTL,
        secure=os.environ.get("SECURE_COOKIES", "").lower() in ("1", "true"),
    )


# Paths reachable without authentication. `/` serves the SPA shell (no session
# granted), `/api/login` exchanges a key for a session, `/api/auth/status` lets
# the front-end discover whether a login is needed.
_PUBLIC_PATHS = {"/", "/health", "/api/login", "/api/auth/status"}


async def auth_middleware(request: Request, call_next):
    if not _APP_API_KEY:
        return await call_next(request)
    # Use the ASGI scope path, not request.url.path, to avoid the Host-header
    # URL-parsing issue in older Starlette releases.
    path = request.scope["path"]
    if path in _PUBLIC_PATHS or path == "/static" or path.startswith("/static/"):
        return await call_next(request)
    if is_authenticated(request):
        return await call_next(request)
    logger.warning("Auth failure: %s %s from %s", request.method, path, request.client.host if request.client else "unknown")
    return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})


async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Skip header injection for SSE streams — middleware buffering kills streaming
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        return response
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
