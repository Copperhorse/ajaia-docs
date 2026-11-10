import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.auth import current_user
from app.documents import router as documents_router
from app.importers import router as import_router
from app.security import hash_password, verify_password
from app.seed import seed_if_empty
from app.sharing import router as sharing_router

log = logging.getLogger("uvicorn.error")

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    log.warning("SECRET_KEY is not set: using a random one, so logins reset on every restart")

# Used when the email is unknown, so "no such user" takes as long as "wrong password".
DUMMY_HASH = hash_password("not-a-real-password")


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    seed_if_empty()
    yield


app = FastAPI(title="Ajaia Docs", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="session",      # cookie is HttpOnly by default
    same_site="lax",
    https_only=os.environ.get("COOKIE_SECURE", "") in ("1", "true", "True"),
    max_age=7 * 24 * 3600,
)


app.include_router(documents_router)
app.include_router(sharing_router)
app.include_router(import_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc):
    # Keep the API promise: errors are always {"detail": "<one readable message>"}.
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"] if p != "body")
    return JSONResponse(status_code=422, content={"detail": f"Invalid {field or 'request'}: {first['msg']}"})


class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/api/login")
def login(body: LoginBody, request: Request):
    email = body.email.strip().lower()
    with db.engine.connect() as conn:
        user = conn.execute(select(db.users).where(db.users.c.email == email)).mappings().first()
    ok = verify_password(body.password, user["password_hash"] if user else DUMMY_HASH)
    if not (user and ok):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    request.session.clear()
    request.session["user_id"] = user["id"]
    return {"id": user["id"], "email": user["email"], "username": user["username"]}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
