from fastapi.testclient import TestClient

from app.main import app
from app.sanitize import content_hash

WELCOME, BOBS_NOTES = 1, 2  # seeded document ids, see conftest.py


# ---------- save then reopen (the minimum test) ----------

def test_save_then_reopen_returns_same_content(login_as):
    alice = login_as("alice")
    doc_id = alice.post("/api/documents", json={"title": "Plan"}).json()["id"]
    html = "<h1>Title</h1><p><strong>bold</strong> <em>it</em> <u>un</u></p><ul><li>a</li></ul>"
    saved = alice.patch(f"/api/documents/{doc_id}", json={"content": html}).json()

    reopened = login_as("alice").get(f"/api/documents/{doc_id}").json()  # fresh client = fresh session
    assert reopened["content"] == html
    assert reopened["content_hash"] == saved["content_hash"] == content_hash(html)
    assert reopened["title"] == "Plan"


def test_requires_login():
    client = TestClient(app)
    assert client.get("/api/documents").status_code == 401
    assert client.get(f"/api/documents/{WELCOME}").status_code == 401


# ---------- permissions ----------

def test_viewer_can_read_but_not_edit_or_rename(login_as):
    carol = login_as("carol")
    doc = carol.get(f"/api/documents/{WELCOME}").json()
    assert doc["role"] == "viewer" and doc["can_edit"] is False
    assert carol.patch(f"/api/documents/{WELCOME}", json={"content": "<p>x</p>"}).status_code == 403
    assert carol.patch(f"/api/documents/{WELCOME}", json={"title": "New"}).status_code == 403
    assert login_as("alice").get(f"/api/documents/{WELCOME}").json()["title"] == "Welcome"  # unchanged


def test_editor_can_edit_and_rename(login_as):
    bob = login_as("bob")
    r = bob.patch(f"/api/documents/{WELCOME}", json={"content": "<p>bob was here</p>", "title": "Renamed"})
    assert r.status_code == 200
    doc = login_as("alice").get(f"/api/documents/{WELCOME}").json()
    assert doc["content"] == "<p>bob was here</p>" and doc["title"] == "Renamed"
    assert doc["updated_by"] == "bob"


def test_stranger_gets_404_everywhere(login_as):
    carol = login_as("carol")  # has no access to Bob's notes
    for r in (carol.get(f"/api/documents/{BOBS_NOTES}"),
              carol.get(f"/api/documents/{BOBS_NOTES}/meta"),
              carol.patch(f"/api/documents/{BOBS_NOTES}", json={"content": "<p>x</p>"}),
              carol.delete(f"/api/documents/{BOBS_NOTES}")):
        assert r.status_code == 404
    # same answer as a document that does not exist, so existence is not revealed
    assert carol.get("/api/documents/999").json() == carol.get(f"/api/documents/{BOBS_NOTES}").json()


def test_only_owner_can_delete(login_as):
    assert login_as("carol").delete(f"/api/documents/{WELCOME}").status_code == 403  # viewer
    assert login_as("bob").delete(f"/api/documents/{WELCOME}").status_code == 403    # editor
    alice = login_as("alice")
    assert alice.delete(f"/api/documents/{WELCOME}").status_code == 200
    assert alice.get(f"/api/documents/{WELCOME}").status_code == 404
    assert login_as("bob").get(f"/api/documents/{WELCOME}").status_code == 404       # shares went too


# ---------- save semantics (change detection) ----------

def test_saving_identical_content_changes_nothing(login_as):
    alice, bob = login_as("alice"), login_as("bob")
    before = alice.get(f"/api/documents/{WELCOME}").json()
    r = bob.patch(f"/api/documents/{WELCOME}", json={"content": before["content"], "base_hash": before["content_hash"]})
    assert r.status_code == 200 and r.json()["content_hash"] == before["content_hash"]
    after = alice.get(f"/api/documents/{WELCOME}").json()
    assert after["updated_by"] == before["updated_by"] == "alice"   # bob's no-op save did not claim authorship
    assert after["updated_at"] == before["updated_at"]


def test_stale_base_hash_gives_409_with_current_version(login_as):
    alice, bob = login_as("alice"), login_as("bob")
    original = alice.get(f"/api/documents/{WELCOME}").json()
    bob.patch(f"/api/documents/{WELCOME}", json={"content": "<p>bob's version</p>", "base_hash": original["content_hash"]})

    r = alice.patch(f"/api/documents/{WELCOME}", json={"content": "<p>alice's version</p>", "base_hash": original["content_hash"]})
    assert r.status_code == 409
    body = r.json()
    assert isinstance(body["detail"], str)
    assert body["current"]["content"] == "<p>bob's version</p>" and body["current"]["updated_by"] == "bob"
    # and nothing was overwritten
    assert alice.get(f"/api/documents/{WELCOME}").json()["content"] == "<p>bob's version</p>"


def test_keep_mine_overwrite_uses_hash_from_409(login_as):
    alice, bob = login_as("alice"), login_as("bob")
    original = alice.get(f"/api/documents/{WELCOME}").json()
    bob.patch(f"/api/documents/{WELCOME}", json={"content": "<p>bob</p>", "base_hash": original["content_hash"]})
    conflict = alice.patch(f"/api/documents/{WELCOME}", json={"content": "<p>alice</p>", "base_hash": original["content_hash"]}).json()

    r = alice.patch(f"/api/documents/{WELCOME}", json={"content": "<p>alice</p>", "base_hash": conflict["current"]["content_hash"]})
    assert r.status_code == 200
    assert alice.get(f"/api/documents/{WELCOME}").json()["content"] == "<p>alice</p>"


def test_save_without_base_hash_is_an_overwrite(login_as):
    alice = login_as("alice")
    assert alice.patch(f"/api/documents/{WELCOME}", json={"content": "<p>forced</p>"}).status_code == 200
    assert alice.get(f"/api/documents/{WELCOME}").json()["content"] == "<p>forced</p>"


def test_new_hash_chains_into_next_save(login_as):
    alice = login_as("alice")
    h = alice.get(f"/api/documents/{WELCOME}").json()["content_hash"]
    h = alice.patch(f"/api/documents/{WELCOME}", json={"content": "<p>one</p>", "base_hash": h}).json()["content_hash"]
    r = alice.patch(f"/api/documents/{WELCOME}", json={"content": "<p>two</p>", "base_hash": h})
    assert r.status_code == 200 and r.json()["content_hash"] == content_hash("<p>two</p>")


def test_content_is_sanitized_on_save(login_as):
    alice = login_as("alice")
    r = alice.patch(f"/api/documents/{WELCOME}", json={"content": '<p onclick="x()">hi</p><script>bad()</script>'})
    assert r.json()["content_hash"] == content_hash("<p>hi</p>")
    assert alice.get(f"/api/documents/{WELCOME}").json()["content"] == "<p>hi</p>"


def test_meta_reports_hash_and_author(login_as):
    bob = login_as("bob")
    bob.patch(f"/api/documents/{WELCOME}", json={"content": "<p>x</p>"})
    meta = login_as("carol").get(f"/api/documents/{WELCOME}/meta").json()
    assert meta["content_hash"] == content_hash("<p>x</p>") and meta["updated_by"] == "bob"


# ---------- validation ----------

def test_title_validation_and_trimming(login_as):
    alice = login_as("alice")
    assert alice.post("/api/documents", json={"title": "   "}).status_code == 400
    assert alice.post("/api/documents", json={"title": "x" * 201}).status_code == 400
    assert alice.patch(f"/api/documents/{WELCOME}", json={"title": ""}).status_code == 400
    assert alice.patch(f"/api/documents/{WELCOME}", json={"title": "  Trimmed  "}).json()["title"] == "Trimmed"
    assert alice.post("/api/documents", json={}).json()["title"] == "Untitled document"


def test_oversized_content_is_rejected_with_413(login_as):
    r = login_as("alice").patch(f"/api/documents/{WELCOME}", json={"content": "a" * 500_001})
    assert r.status_code == 413 and "too large" in r.json()["detail"]


# ---------- list ----------

def test_list_splits_owned_and_shared(login_as):
    alice = login_as("alice").get("/api/documents").json()
    assert [d["title"] for d in alice["owned"]] == ["Welcome"]
    assert alice["owned"][0]["share_count"] == 2 and alice["owned"][0]["role"] == "owner"
    assert "Welcome to Ajaia Docs" in alice["owned"][0]["preview"]
    assert [(d["title"], d["role"], d["owner"]) for d in alice["shared"]] == [("Bob's notes", "editor", "bob")]

    carol = login_as("carol").get("/api/documents").json()
    assert carol["owned"] == []
    assert [(d["title"], d["role"], d["owner"]) for d in carol["shared"]] == [("Welcome", "viewer", "alice")]
