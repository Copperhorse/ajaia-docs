"""Demo data, created only when the users table is empty (first start)."""
import os

from sqlalchemy import func, insert, select

from app import db
from app.sanitize import content_hash, sanitize_html
from app.security import hash_password

WELCOME_HTML = (
    "<h1>Welcome to Ajaia Docs</h1>"
    "<p>This is a <strong>shared</strong> demo document. Try <em>formatting</em>, "
    "<u>underline</u> and lists:</p>"
    "<ul><li>Bullet one</li><li>Bullet two</li></ul>"
)
BOB_HTML = "<h2>Bob's notes</h2><p>Alice can edit this document.</p>"


def _add_doc(conn, owner_id, title, html):
    clean = sanitize_html(html)
    return conn.execute(insert(db.documents).values(
        owner_id=owner_id, title=title, content=clean,
        content_hash=content_hash(clean), updated_by=owner_id,
    )).inserted_primary_key[0]


def seed_if_empty():
    with db.engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(db.users)).scalar() > 0:
            return
        password = os.environ.get("SEED_PASSWORD")
        if not password:
            raise RuntimeError("Database is empty and SEED_PASSWORD is not set; cannot create demo users")
        pw_hash = hash_password(password)
        ids = {}
        for name in ("alice", "bob", "carol"):
            ids[name] = conn.execute(insert(db.users).values(
                email=f"{name}@example.com", username=name, password_hash=pw_hash,
            )).inserted_primary_key[0]

        welcome = _add_doc(conn, ids["alice"], "Welcome", WELCOME_HTML)
        notes = _add_doc(conn, ids["bob"], "Bob's notes", BOB_HTML)
        conn.execute(insert(db.shares), [
            {"document_id": welcome, "user_id": ids["bob"], "role": "editor"},
            {"document_id": welcome, "user_id": ids["carol"], "role": "viewer"},
            {"document_id": notes, "user_id": ids["alice"], "role": "editor"},
        ])
