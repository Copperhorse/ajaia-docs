"""Sharing endpoints. Only the owner can see or change who a document is shared with."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, insert, select, update

from app import db
from app.auth import current_user, normalize_email
from app.documents import load_document

router = APIRouter(prefix="/api/documents/{doc_id}/shares")

shares, users = db.shares, db.users


class ShareBody(BaseModel):
    email: str
    role: str


def owner_only(conn, doc_id: int, user: dict):
    doc, role = load_document(conn, doc_id, user)  # 404 if the user cannot see the document at all
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can manage sharing")
    return doc


def find_user(conn, email: str):
    user = conn.execute(select(users.c.id, users.c.email, users.c.username)
                        .where(users.c.email == normalize_email(email))).mappings().first()
    if user is None:
        raise HTTPException(status_code=404, detail="No user with that email")
    return user


@router.get("")
def list_shares(doc_id: int, user: dict = Depends(current_user)):
    with db.engine.connect() as conn:
        owner_only(conn, doc_id, user)
        rows = conn.execute(
            select(users.c.email, users.c.username, shares.c.role)
            .join(users, users.c.id == shares.c.user_id)
            .where(shares.c.document_id == doc_id)
            .order_by(users.c.email)
        ).mappings().all()
    return [dict(r) for r in rows]


@router.put("")
def grant_access(doc_id: int, body: ShareBody, user: dict = Depends(current_user)):
    """Give someone access, or change their role if they already have it."""
    if body.role not in ("viewer", "editor"):
        raise HTTPException(status_code=400, detail="Role must be 'viewer' or 'editor'")
    with db.engine.begin() as conn:
        owner_only(conn, doc_id, user)
        target = find_user(conn, body.email)
        if target["id"] == user["id"]:
            raise HTTPException(status_code=400, detail="You already own this document")
        already = conn.execute(select(shares.c.role).where(
            shares.c.document_id == doc_id, shares.c.user_id == target["id"])).scalar()
        if already is None:
            conn.execute(insert(shares).values(document_id=doc_id, user_id=target["id"], role=body.role))
        else:
            conn.execute(update(shares).where(
                shares.c.document_id == doc_id, shares.c.user_id == target["id"]).values(role=body.role))
    return {"email": target["email"], "username": target["username"], "role": body.role}


@router.delete("/{email}")
def remove_access(doc_id: int, email: str, user: dict = Depends(current_user)):
    with db.engine.begin() as conn:
        owner_only(conn, doc_id, user)
        target = find_user(conn, email)
        removed = conn.execute(delete(shares).where(
            shares.c.document_id == doc_id, shares.c.user_id == target["id"])).rowcount
        if removed == 0:
            raise HTTPException(status_code=404, detail="That user does not have access to this document")
    return {"ok": True}
