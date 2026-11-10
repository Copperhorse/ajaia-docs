import base64
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import app

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def make_docx(body_xml: str, with_image=False) -> bytes:
    """Smallest .docx mammoth will read: a zip of a few XML files."""
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            + ('<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>' if with_image else "")
            + "</Relationships>")
    files = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/_rels/document.xml.rels": rels,
        "word/styles.xml": f'<w:styles {NS}><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style></w:styles>',
        "word/document.xml": f"<w:document {NS}><w:body>{body_xml}</w:body></w:document>",
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
        if with_image:
            z.writestr("word/media/image1.png", PNG_1X1)
    return out.getvalue()


IMAGE_XML = ('<w:p><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
             '<wp:extent cx="100" cy="100"/><wp:docPr id="1" name="p"/>'
             '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
             '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
             '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rId2"/></pic:blipFill></pic:pic>'
             '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')


def upload(client, name, data):
    return client.post("/api/import", files={"file": (name, data)})


def opened(client, doc_id):
    return client.get(f"/api/documents/{doc_id}").json()


# ---------- the three supported types ----------

def test_txt_import_creates_owned_document(login_as):
    alice = login_as("alice")
    r = upload(alice, "My notes.txt", b"First paragraph\nsecond line\n\nSecond paragraph")
    assert r.status_code == 200 and r.json()["title"] == "My notes"
    doc = opened(alice, r.json()["id"])
    assert doc["content"] == "<p>First paragraph<br>second line</p><p>Second paragraph</p>"
    assert doc["role"] == "owner"
    assert "My notes" in [d["title"] for d in alice.get("/api/documents").json()["owned"]]


def test_txt_html_is_shown_as_text_not_executed(login_as):
    alice = login_as("alice")
    doc_id = upload(alice, "x.txt", b"<script>alert(1)</script><b>hi</b>").json()["id"]
    content = opened(alice, doc_id)["content"]
    assert "<script>" not in content and "<b>" not in content
    assert "&lt;script&gt;" in content  # visible as plain text


def test_md_import_keeps_basic_formatting_and_sanitizes(login_as):
    alice = login_as("alice")
    md = b"# Title\n\n**bold** and *italic*\n\n- one\n- two\n\n<script>bad()</script>"
    content = opened(alice, upload(alice, "readme.md", md).json()["id"])["content"]
    assert "<h1>Title</h1>" in content and "<strong>bold</strong>" in content and "<em>italic</em>" in content
    assert "<li>one</li>" in content and "script" not in content


def test_docx_import_keeps_heading_and_bold(login_as):
    alice = login_as("alice")
    body = ('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Report</w:t></w:r></w:p>'
            '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>important</w:t></w:r><w:r><w:t> text</w:t></w:r></w:p>')
    r = upload(alice, "Quarterly Report.docx", make_docx(body))
    assert r.status_code == 200 and r.json()["title"] == "Quarterly Report" and r.json()["warnings"] == []
    content = opened(alice, r.json()["id"])["content"]
    assert content == "<h1>Report</h1><p><strong>important</strong> text</p>"


def test_docx_images_are_dropped_but_text_is_kept(login_as):
    alice = login_as("alice")
    body = '<w:p><w:r><w:t>before</w:t></w:r></w:p>' + IMAGE_XML
    r = upload(alice, "pic.docx", make_docx(body, with_image=True))
    assert r.status_code == 200
    content = opened(alice, r.json()["id"])["content"]
    assert "before" in content and "<img" not in content and "base64" not in content


# ---------- decoding ----------

def test_text_decoding_utf8_bom_utf16_latin1(login_as):
    alice = login_as("alice")
    cases = {
        "utf8-bom": "café".encode("utf-8-sig"),
        "utf16": "café".encode("utf-16"),          # Python adds a BOM
        "latin1": "café".encode("latin-1"),
    }
    for name, data in cases.items():
        doc_id = upload(alice, f"{name}.txt", data).json()["id"]
        assert opened(alice, doc_id)["content"] == "<p>café</p>", name


# ---------- rejections ----------

def test_wrong_type_gets_415(login_as):
    alice = login_as("alice")
    for name in ("report.pdf", "image.png", "noextension", "script.html", "archive.txt.exe"):
        r = upload(alice, name, b"hello")
        assert r.status_code == 415, name
        assert ".txt, .md or .docx" in r.json()["detail"]


def test_empty_file_gets_400(login_as):
    alice = login_as("alice")
    assert upload(alice, "empty.txt", b"").status_code == 400
    assert upload(alice, "blank.md", b"  \n \n").status_code == 400
    assert upload(alice, "empty.docx", b"").status_code == 400


def test_oversize_upload_gets_413(login_as):
    r = upload(login_as("alice"), "big.txt", b"a" * (2 * 1024 * 1024 + 1))
    assert r.status_code == 413 and "2 MB" in r.json()["detail"]


def test_text_over_document_limit_gets_413(login_as):
    # Under the 2 MB upload limit, but over the 500,000-character document limit.
    alice = login_as("alice")
    r = upload(alice, "long.txt", b"a" * 600_000)
    assert r.status_code == 413 and "500,000 characters" in r.json()["detail"]
    assert upload(alice, "fits.txt", b"a" * 400_000).status_code == 200


def test_fake_and_corrupt_docx_get_400(login_as):
    alice = login_as("alice")
    assert upload(alice, "fake.docx", b"this is plain text, not a zip").status_code == 400
    assert upload(alice, "bad.docx", make_docx("<w:p/>")[:200]).status_code == 400   # truncated zip
    no_document_xml = io.BytesIO()
    with zipfile.ZipFile(no_document_xml, "w") as z:
        z.writestr("hello.txt", "hi")
    r = upload(alice, "empty-zip.docx", no_document_xml.getvalue())
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)


def test_zip_bomb_docx_is_rejected(login_as):
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"\0" * (21 * 1024 * 1024))   # tiny on disk, 21 MB unpacked
    assert len(bomb.getvalue()) < 100_000
    r = upload(login_as("alice"), "bomb.docx", bomb.getvalue())
    assert r.status_code == 400 and "too large once unpacked" in r.json()["detail"]


def test_docx_with_no_text_gets_400(login_as):
    r = upload(login_as("alice"), "blank.docx", make_docx("<w:p/>"))
    assert r.status_code == 400


def test_import_requires_login():
    assert upload(TestClient(app), "a.txt", b"hello").status_code == 401


def test_filename_with_path_is_reduced_to_a_title(login_as):
    alice = login_as("alice")
    r = upload(alice, "../../etc/evil.txt", b"hello")
    assert r.json()["title"] == "evil"
