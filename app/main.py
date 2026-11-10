import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
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


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# A display name: letters (any language), digits, spaces, and . _ - ' with at least one letter or digit.
NAME_PATTERN = re.compile(r"^(?=.*\w)[\w .'’-]{2,30}$")


class RegisterBody(BaseModel):
    email: str
    username: str
    password: str


@app.post("/api/register", status_code=201)
def register(body: RegisterBody, request: Request):
    """Open sign-up: anyone can create an account. No email verification (see SPEC section 16)."""
    email = body.email.strip().lower()
    username = " ".join(body.username.split())  # trim and collapse runs of spaces; capitals are kept
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    if not NAME_PATTERN.match(username):
        raise HTTPException(status_code=400, detail="Name must be 2 to 30 characters: letters, numbers, spaces, dots, dashes, apostrophes or underscores")
    if not 8 <= len(body.password) <= 128:
        raise HTTPException(status_code=400, detail="Password must be 8 to 128 characters")

    password_hash = hash_password(body.password)
    try:
        with db.engine.begin() as conn:
            if conn.execute(select(db.users.c.id).where(db.users.c.email == email)).first():
                raise HTTPException(status_code=409, detail="An account with that email already exists")
            # compared ignoring case, the same way the unique index does it
            if conn.execute(select(db.users.c.id).where(func.lower(db.users.c.username) == func.lower(username))).first():
                raise HTTPException(status_code=409, detail="That name is taken")
            user_id = conn.execute(insert(db.users).values(
                email=email, username=username, password_hash=password_hash,
            )).inserted_primary_key[0]
    except IntegrityError:  # two sign-ups with the same email or name at the same instant
        raise HTTPException(status_code=409, detail="That email or name is already taken")

    request.session.clear()
    request.session["user_id"] = user_id  # signed in straight away
    return {"id": user_id, "email": email, "username": username}


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


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")
