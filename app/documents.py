"""Document endpoints: create, list, open, save (with change detection), rename, delete."""
import html
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import aliased

from app import db
from app.auth import current_user
from app.sanitize import ContentTooLarge, content_hash, sanitize_html

router = APIRouter(prefix="/api/documents")

docs, shares, users = db.documents, db.shares, db.users


# ---------- helpers ----------

def clean_title(title: str) -> str:
    title = title.strip()
    if not 1 <= len(title) <= 200:
        raise HTTPException(status_code=400, detail="Title must be 1 to 200 characters")
    return title


def load_document(conn, doc_id: int, user: dict):
    """Return (document row, role). Role is owner, editor or viewer.
    A missing document and a document the user cannot see give the same 404."""
    doc = conn.execute(select(docs).where(docs.c.id == doc_id)).mappings().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["owner_id"] == user["id"]:
        return doc, "owner"
    role = conn.execute(
        select(shares.c.role).where(shares.c.document_id == doc_id, shares.c.user_id == user["id"])
    ).scalar()
    if role is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc, role


def username(conn, user_id):
    if user_id is None:
        return None
    return conn.execute(select(users.c.username).where(users.c.id == user_id)).scalar()


def preview(content: str, length: int = 120) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", content))  # content is already sanitized HTML
    return " ".join(text.split())[:length]


def snapshot(conn, doc_id: int) -> dict:
    """The current saved version, sent with a 409 so the browser can show it without another request."""
    doc = conn.execute(select(docs).where(docs.c.id == doc_id)).mappings().one()
    return {
        "content": doc["content"],
        "content_hash": doc["content_hash"],
        "updated_by": username(conn, doc["updated_by"]),
        "updated_at": doc["updated_at"],
    }


# ---------- request bodies ----------

class CreateBody(BaseModel):
    title: str | None = None


class SaveBody(BaseModel):
    title: str | None = None
    content: str | None = None
    base_hash: str | None = None


# ---------- endpoints ----------

@router.post("")
def create_document(body: CreateBody, user: dict = Depends(current_user)):
    title = clean_title(body.title) if body.title is not None else "Untitled document"
    with db.engine.begin() as conn:
        doc_id = conn.execute(insert(docs).values(
            owner_id=user["id"], title=title, content="",
            content_hash=content_hash(""), updated_by=user["id"],
        )).inserted_primary_key[0]
    return {"id": doc_id, "title": title}


@router.get("")
def list_documents(user: dict = Depends(current_user)):
    owner = aliased(users)
    all_shares = aliased(shares)  # separate alias: the "shared" query below joins `shares` itself
    share_count = (select(func.count()).select_from(all_shares)
                   .where(all_shares.c.document_id == docs.c.id).scalar_subquery())
    base = (select(docs.c.id, docs.c.title, docs.c.content, docs.c.updated_at,
                   owner.c.username.label("owner"), share_count.label("share_count"))
            .join(owner, owner.c.id == docs.c.owner_id)
            .order_by(docs.c.updated_at.desc(), docs.c.id.desc()))

    def rows_to_dicts(rows, role=None):
        return [{"id": r["id"], "title": r["title"], "preview": preview(r["content"]),
                 "updated_at": r["updated_at"], "owner": r["owner"], "share_count": r["share_count"],
                 "role": role or r["role"]} for r in rows]

    with db.engine.connect() as conn:
        owned = conn.execute(base.where(docs.c.owner_id == user["id"])).mappings().all()
        shared = conn.execute(
            base.add_columns(shares.c.role)
            .join(shares, shares.c.document_id == docs.c.id)
            .where(shares.c.user_id == user["id"])
        ).mappings().all()
    return {"owned": rows_to_dicts(owned, "owner"), "shared": rows_to_dicts(shared)}


@router.get("/{doc_id}")
def get_document(doc_id: int, user: dict = Depends(current_user)):
    with db.engine.connect() as conn:
        doc, role = load_document(conn, doc_id, user)
        return {
            "id": doc["id"], "title": doc["title"], "content": doc["content"],
            "content_hash": doc["content_hash"], "role": role, "can_edit": role != "viewer",
            "owner": username(conn, doc["owner_id"]),
            "updated_by": username(conn, doc["updated_by"]), "updated_at": doc["updated_at"],
        }


@router.get("/{doc_id}/meta")
def get_meta(doc_id: int, user: dict = Depends(current_user)):
    """Small response for the browser's 10-second polling."""
    with db.engine.connect() as conn:
        doc, _ = load_document(conn, doc_id, user)
        return {"content_hash": doc["content_hash"], "updated_at": doc["updated_at"],
                "updated_by": username(conn, doc["updated_by"])}


@router.patch("/{doc_id}")
def save_document(doc_id: int, body: SaveBody, user: dict = Depends(current_user)):
    """Save title and/or content. Content follows SPEC section 7 (change detection)."""
    with db.engine.begin() as conn:
        doc, role = load_document(conn, doc_id, user)
        if role == "viewer":
            raise HTTPException(status_code=403, detail="You have view-only access to this document")

        changes = {}
        if body.title is not None:
            title = clean_title(body.title)
            if title != doc["title"]:
                changes["title"] = title

        content_changed = False
        if body.content is not None:
            try:
                clean = sanitize_html(body.content)                       # step 1
            except ContentTooLarge as e:
                raise HTTPException(status_code=413, detail=str(e))
            new_hash = content_hash(clean)
            if new_hash != doc["content_hash"]:                           # step 3: same content = do nothing
                if body.base_hash is not None and body.base_hash != doc["content_hash"]:
                    return conflict(conn, doc_id)                         # step 4
                changes.update(content=clean, content_hash=new_hash)
                content_changed = True

        if changes:
            changes.update(updated_by=user["id"], updated_at=func.now())
            stmt = update(docs).where(docs.c.id == doc_id)
            if content_changed:
                # step 5, compare-and-swap: only write if nobody saved since we read the row
                stmt = stmt.where(docs.c.content_hash == doc["content_hash"])
            if conn.execute(stmt.values(**changes)).rowcount == 0:
                return conflict(conn, doc_id)

        saved = conn.execute(select(docs.c.title, docs.c.content_hash, docs.c.updated_at)
                             .where(docs.c.id == doc_id)).mappings().one()
        return dict(saved)


def conflict(conn, doc_id: int) -> JSONResponse:
    return JSONResponse(status_code=409, content=jsonable_encoder({
        "detail": "Someone else saved a newer version of this document",
        "current": snapshot(conn, doc_id),
    }))


@router.delete("/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(current_user)):
    with db.engine.begin() as conn:
        _, role = load_document(conn, doc_id, user)
        if role != "owner":
            raise HTTPException(status_code=403, detail="Only the owner can delete this document")
        conn.execute(delete(docs).where(docs.c.id == doc_id))  # shares go too (ON DELETE CASCADE)
    return {"ok": True}
