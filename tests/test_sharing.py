WELCOME, BOBS_NOTES = 1, 2  # seeded ids, see conftest.py


def share(client, doc_id, email, role):
    return client.put(f"/api/documents/{doc_id}/shares", json={"email": email, "role": role})


def test_owner_lists_shares(login_as):
    r = login_as("alice").get(f"/api/documents/{WELCOME}/shares")
    assert r.status_code == 200
    assert [(s["email"], s["role"]) for s in r.json()] == [("bob@example.com", "editor"), ("carol@example.com", "viewer")]


def test_share_then_recipient_sees_it_under_shared(login_as):
    bob = login_as("bob")
    assert share(bob, BOBS_NOTES, "carol@example.com", "viewer").status_code == 200
    carol = login_as("carol")
    assert ("Bob's notes", "viewer", "bob") in [(d["title"], d["role"], d["owner"]) for d in carol.get("/api/documents").json()["shared"]]
    assert carol.get(f"/api/documents/{BOBS_NOTES}").json()["can_edit"] is False


def test_changing_role_updates_instead_of_duplicating(login_as):
    alice = login_as("alice")
    assert share(alice, WELCOME, "carol@example.com", "editor").status_code == 200  # was viewer
    roles = {s["email"]: s["role"] for s in alice.get(f"/api/documents/{WELCOME}/shares").json()}
    assert roles == {"bob@example.com": "editor", "carol@example.com": "editor"}
    assert login_as("carol").patch(f"/api/documents/{WELCOME}", json={"content": "<p>now I can</p>"}).status_code == 200


def test_email_is_case_and_space_insensitive(login_as):
    r = share(login_as("bob"), BOBS_NOTES, "  CAROL@Example.com ", "viewer")
    assert r.status_code == 200 and r.json()["email"] == "carol@example.com"


def test_validation_errors(login_as):
    alice = login_as("alice")
    assert share(alice, WELCOME, "nobody@example.com", "viewer").status_code == 404   # unknown email
    assert share(alice, WELCOME, "alice@example.com", "viewer").status_code == 400    # yourself
    assert share(alice, WELCOME, "bob@example.com", "admin").status_code == 400       # bad role
    for r in (share(alice, WELCOME, "nobody@example.com", "viewer"), share(alice, WELCOME, "alice@example.com", "viewer")):
        assert isinstance(r.json()["detail"], str)


def test_only_owner_can_manage_sharing(login_as):
    for name in ("bob", "carol"):  # editor and viewer of Welcome
        c = login_as(name)
        assert c.get(f"/api/documents/{WELCOME}/shares").status_code == 403
        assert share(c, WELCOME, "carol@example.com", "editor").status_code == 403
        assert c.delete(f"/api/documents/{WELCOME}/shares/carol@example.com").status_code == 403
    # nothing changed
    roles = {s["email"]: s["role"] for s in login_as("alice").get(f"/api/documents/{WELCOME}/shares").json()}
    assert roles["carol@example.com"] == "viewer"


def test_stranger_gets_404_on_sharing_endpoints(login_as):
    carol = login_as("carol")  # no access to Bob's notes
    assert carol.get(f"/api/documents/{BOBS_NOTES}/shares").status_code == 404
    assert share(carol, BOBS_NOTES, "carol@example.com", "editor").status_code == 404
    assert carol.delete(f"/api/documents/{BOBS_NOTES}/shares/alice@example.com").status_code == 404


def test_remove_access_then_user_gets_404(login_as):
    alice, carol = login_as("alice"), login_as("carol")
    assert carol.get(f"/api/documents/{WELCOME}").status_code == 200
    assert alice.delete(f"/api/documents/{WELCOME}/shares/carol@example.com").status_code == 200
    assert carol.get(f"/api/documents/{WELCOME}").status_code == 404
    assert alice.get("/api/documents").json()["owned"][0]["share_count"] == 1
    # removing someone who has no access, or does not exist
    assert alice.delete(f"/api/documents/{WELCOME}/shares/carol@example.com").status_code == 404
    assert alice.delete(f"/api/documents/{WELCOME}/shares/nobody@example.com").status_code == 404
