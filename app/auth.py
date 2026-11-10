"""Who is signed in? The session cookie holds only the user id; the user is looked up on every request."""
from fastapi import HTTPException, Request
from sqlalchemy import select

from app import db


def normalize_email(raw: str) -> str:
    """The one rule for comparing emails: ignore surrounding spaces and capitals."""
    return raw.strip().lower()


def current_user(request: Request) -> dict:
    """FastAPI dependency: the signed-in user as a dict, or 401."""
    user_id = request.session.get("user_id")
    if user_id is not None:
        with db.engine.connect() as conn:
            row = conn.execute(
                select(db.users.c.id, db.users.c.email, db.users.c.username)
                .where(db.users.c.id == user_id)
            ).mappings().first()
        if row:
            return dict(row)
    request.session.clear()
    raise HTTPException(status_code=401, detail="Please sign in")
