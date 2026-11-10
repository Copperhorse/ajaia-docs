"""Import a .txt, .md or .docx file as a new document (SPEC section 8)."""
import html
import io
import zipfile
from pathlib import PurePath

import mammoth
import markdown
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import insert

from app import db
from app.auth import current_user
from app.sanitize import ContentTooLarge, content_hash, sanitize_html

router = APIRouter()

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DOCX_UNPACKED_BYTES = 20 * 1024 * 1024
SUPPORTED = (".txt", ".md", ".docx")


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM) first. UTF-16 only if it has a BOM. Otherwise Latin-1, which never fails."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def txt_to_html(text: str) -> str:
    """Blank line = new paragraph, single newline = line break. Everything is escaped, so it is plain text."""
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n")]
    return "".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in paragraphs if p)


def md_to_html(text: str) -> str:
    return markdown.markdown(text)  # raw HTML inside the Markdown is allowed here, the sanitizer cleans it later


def docx_to_html(data: bytes):
    """Return (html, warnings). Rejects fake, corrupt and zip-bomb files with a 400."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(info.file_size for info in z.infolist()) > MAX_DOCX_UNPACKED_BYTES:
                raise HTTPException(status_code=400, detail="This .docx is too large once unpacked (limit 20 MB)")
        # Images are dropped: we do not support them, and base64 images would bloat the HTML past the size limit.
        result = mammoth.convert_to_html(io.BytesIO(data), convert_image=lambda image: [])
    except HTTPException:
        raise
    except Exception:  # untrusted file: any parse failure means "not a usable .docx"
        raise HTTPException(status_code=400, detail="Could not read this file as a .docx document")
    return result.value, sorted({m.message for m in result.messages})


def title_from_filename(filename: str) -> str:
    stem = PurePath(filename).stem.strip()[:200]
    return stem or "Imported document"


@router.post("/api/import")
def import_file(file: UploadFile, user: dict = Depends(current_user)):
    filename = PurePath(file.filename or "").name
    extension = PurePath(filename).suffix.lower()
    if extension not in SUPPORTED:
        raise HTTPException(status_code=415, detail="Unsupported file type. Please upload a .txt, .md or .docx file")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)  # never read more than the limit plus one byte
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (limit 2 MB)")
    if not data.strip():
        raise HTTPException(status_code=400, detail="The file is empty")

    warnings = []
    if extension == ".docx":
        raw_html, warnings = docx_to_html(data)
    elif extension == ".md":
        raw_html = md_to_html(decode_text(data))
    else:
        raw_html = txt_to_html(decode_text(data))

    try:
        content = sanitize_html(raw_html)
    except ContentTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    if not content.strip():
        raise HTTPException(status_code=400, detail="No text could be imported from this file")

    title = title_from_filename(filename)
    with db.engine.begin() as conn:
        doc_id = conn.execute(insert(db.documents).values(
            owner_id=user["id"], title=title, content=content,
            content_hash=content_hash(content), updated_by=user["id"],
        )).inserted_primary_key[0]
    return {"id": doc_id, "title": title, "warnings": warnings}
