import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.main import app

WELCOME = 1  # seeded document, see conftest.py


def insert_user(email, username):
    """Put a user straight into the database, past the sign-up route."""
    with db.engine.begin() as conn:
        conn.execute(insert(db.users).values(email=email, username=username, password_hash="h"))


def sign_up(client, email="newbie@example.com", username="newbie", password="a-good-password"):
    return client.post("/api/register", json={"email": email, "username": username, "password": password})


def test_sign_up_creates_account_and_signs_in():
    client = TestClient(app)
    r = sign_up(client)
    assert r.status_code == 201
    assert r.json()["email"] == "newbie@example.com" and r.json()["username"] == "newbie"
    assert "password" not in str(r.json())
    assert client.get("/api/me").json()["username"] == "newbie"       # already signed in


def test_new_user_can_sign_in_again_and_password_is_stored_hashed():
    sign_up(TestClient(app))
    fresh = TestClient(app)
    assert fresh.post("/api/login", json={"email": "newbie@example.com", "password": "a-good-password"}).status_code == 200
    assert fresh.post("/api/login", json={"email": "newbie@example.com", "password": "wrong-password"}).status_code == 401
    with db.engine.connect() as conn:
        stored = conn.execute(select(db.users.c.password_hash).where(db.users.c.username == "newbie")).scalar()
    assert stored.startswith("scrypt$") and "a-good-password" not in stored


def test_email_is_cleaned_up_and_name_keeps_its_capitals_and_spaces():
    r = sign_up(TestClient(app), email="  Mixed.Case@Example.COM ", username="  Bob    Odenkirk ")
    assert r.status_code == 201
    assert r.json()["email"] == "mixed.case@example.com"   # emails are lowercased
    assert r.json()["username"] == "Bob Odenkirk"           # names are shown as typed, with spaces tidied


def test_names_with_spaces_capitals_accents_and_apostrophes_are_accepted():
    client = TestClient(app)
    for i, name in enumerate(["Bob Odenkirk", "José Müller", "O'Brien", "a_b-c.d", "李雷", "Ab"]):
        r = sign_up(client, email=f"person{i}@example.com", username=name)
        assert r.status_code == 201 and r.json()["username"] == name, name
        assert client.get("/api/me").json()["username"] == name


def test_the_name_people_see_is_the_one_that_was_typed(login_as):
    sign_up(TestClient(app), email="sue@example.com", username="Sue Smith")
    alice = login_as("alice")
    alice.put(f"/api/documents/{WELCOME}/shares", json={"email": "sue@example.com", "role": "viewer"})
    names = {p["email"]: p["username"] for p in alice.get(f"/api/documents/{WELCOME}/shares").json()}
    assert names["sue@example.com"] == "Sue Smith"


def test_duplicate_email_and_name_are_refused(login_as):
    client = TestClient(app)
    r = sign_up(client, email="ALICE@example.com", username="someone else")      # alice is seeded
    assert r.status_code == 409 and r.json() == {"detail": "An account with that email already exists"}
    for i, taken in enumerate(["alice", "Alice", "ALICE", "  aLiCe  "]):          # names clash ignoring case
        r = sign_up(client, email=f"fresh{i}@example.com", username=taken)
        assert r.status_code == 409 and r.json() == {"detail": "That name is taken"}, taken
    assert client.get("/api/me").status_code == 401                              # a refused sign-up does not sign anyone in


def test_the_database_itself_refuses_names_that_differ_only_by_case():
    with pytest.raises(IntegrityError):
        insert_user("x@example.com", "BOB")                                      # "bob" is seeded


def test_init_db_adds_the_index_to_a_database_that_already_has_its_tables():
    # A database made before this rule (like an existing Supabase one) has the tables but not the index.
    with db.engine.begin() as conn:
        conn.execute(text("DROP INDEX users_username_lower_idx"))
    insert_user("x@example.com", "BOB")                                          # no longer refused
    with db.engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email = 'x@example.com'"))
    db.init_db()                                                                  # the "existing database" path
    db.init_db()                                                                  # and it is safe to run again
    with pytest.raises(IntegrityError):
        insert_user("y@example.com", "BOB")


def test_invalid_input_gets_a_clear_400():
    client = TestClient(app)
    for email in ("", "not-an-email", "a@b", "two words@example.com", "x" * 250 + "@example.com"):
        assert sign_up(client, email=email).status_code == 400, email
    for name in ("", " ", "a", "x" * 31, "semi;colon", "<script>", "a@b.c", "!!", "..", "a/b", "tab\x00nul"):
        assert sign_up(client, username=name).status_code == 400, name
    assert sign_up(client, username="x" * 31).json() == {
        "detail": "Name must be 2 to 30 characters: letters, numbers, spaces, dots, dashes, apostrophes or underscores"}
    for password in ("", "short", "x" * 129):
        assert sign_up(client, password=password).status_code == 400, password
    r = sign_up(client, password="short")
    assert r.json() == {"detail": "Password must be 8 to 128 characters"}
    assert client.post("/api/register", json={"email": "a@b.co"}).status_code == 422   # missing fields


def test_password_length_limits_are_inclusive():
    client = TestClient(app)
    assert sign_up(client, username="eight", email="eight@example.com", password="12345678").status_code == 201
    assert sign_up(client, username="long", email="long@example.com", password="x" * 128).status_code == 201


def test_new_user_starts_empty_and_cannot_see_other_documents():
    client = TestClient(app)
    sign_up(client)
    assert client.get("/api/documents").json() == {"owned": [], "shared": []}
    assert client.get(f"/api/documents/{WELCOME}").status_code == 404


def test_new_user_can_be_shared_with_by_email(login_as):
    sign_up(TestClient(app))
    alice = login_as("alice")
    assert alice.put(f"/api/documents/{WELCOME}/shares", json={"email": "newbie@example.com", "role": "editor"}).status_code == 200
    newbie = TestClient(app)
    newbie.post("/api/login", json={"email": "newbie@example.com", "password": "a-good-password"})
    assert newbie.get(f"/api/documents/{WELCOME}").json()["role"] == "editor"
