import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import db
from app.main import app

PASSWORD = "test-password"  # set as SEED_PASSWORD in conftest.py


@pytest.fixture
def client():
    with TestClient(app) as c:  # entering the context runs startup: create tables + seed
        yield c


def login(client, email="alice@example.com", password=PASSWORD):
    return client.post("/api/login", json={"email": email, "password": password})


def test_seed_created_demo_data(client):
    with db.engine.connect() as conn:
        count = lambda t: conn.execute(select(func.count()).select_from(t)).scalar()
        assert (count(db.users), count(db.documents), count(db.shares)) == (3, 2, 3)


def test_login_then_me(client):
    r = login(client)
    assert r.status_code == 200 and r.json()["email"] == "alice@example.com"
    assert "password_hash" not in r.json()
    assert client.get("/api/me").json()["username"] == "alice"


def test_login_email_is_case_and_space_insensitive(client):
    assert login(client, email="  Alice@Example.COM ").status_code == 200


def test_wrong_password_and_unknown_email_give_same_message(client):
    for r in (login(client, password="nope"), login(client, email="nobody@example.com")):
        assert r.status_code == 401
        assert r.json() == {"detail": "Wrong email or password"}


def test_me_requires_login(client):
    r = client.get("/api/me")
    assert r.status_code == 401 and r.json() == {"detail": "Please sign in"}


def test_logout_ends_session(client):
    login(client)
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_session_cookie_is_httponly_and_samesite(client):
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.json() == {"status": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_validation_error_is_a_plain_detail_string(client):
    r = client.post("/api/login", json={"email": "a@b.com"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
