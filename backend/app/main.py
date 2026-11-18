import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()  # fails fast with a clear message when required configuration is missing

app = FastAPI(title=settings.APP_NAME, docs_url="/api/docs" if settings.APP_ENV != "production" else None,
              openapi_url="/api/openapi.json" if settings.APP_ENV != "production" else None)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_hits: dict[str, deque] = defaultdict(deque)
RATE_LIMIT = (300, 60.0)  # requests per window (seconds) per client
LOGIN_RATE_LIMIT = (10, 60.0)


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and request.method not in SAFE_METHODS:
        # CSRF: browsers cannot add this header to a cross-site request without CORS, which is not enabled.
        if request.headers.get("x-requested-with") != "presales":
            return JSONResponse({"detail": "Missing request header"}, status_code=403)
    client = request.client.host if request.client else "?"
    limit, window = LOGIN_RATE_LIMIT if path == "/api/auth/login" else RATE_LIMIT
    key = f"{client}:{'login' if path == '/api/auth/login' else 'all'}"
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return JSONResponse({"detail": "Too many requests. Wait a minute and try again."}, status_code=429)
    q.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/api/health")
def health():
    from sqlalchemy import text

    from app.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.APP_ENV}


from app.modules import register_routers  # noqa: E402

register_routers(app)
