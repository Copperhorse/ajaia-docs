from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.main import app

WELCOME = 1  # seeded document, see conftest.py


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


def test_email_and_username_are_cleaned_up():
    r = sign_up(TestClient(app), email="  Mixed.Case@Example.COM ", username="  Mixed_Name ")
    assert r.status_code == 201
    assert r.json()["email"] == "mixed.case@example.com" and r.json()["username"] == "mixed_name"


def test_duplicate_email_and_username_are_refused(login_as):
    client = TestClient(app)
    r = sign_up(client, email="ALICE@example.com", username="someone-else")      # alice is seeded
    assert r.status_code == 409 and r.json() == {"detail": "An account with that email already exists"}
    r = sign_up(client, email="fresh@example.com", username="Alice")
    assert r.status_code == 409 and r.json() == {"detail": "That username is taken"}
    assert client.get("/api/me").status_code == 401                              # a refused sign-up does not sign anyone in


def test_invalid_input_gets_a_clear_400():
    client = TestClient(app)
    for email in ("", "not-an-email", "a@b", "two words@example.com", "x" * 250 + "@example.com"):
        assert sign_up(client, email=email).status_code == 400, email
    for username in ("", "a", "x" * 31, "has space", "semi;colon", "<script>"):
        assert sign_up(client, username=username).status_code == 400, username
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
