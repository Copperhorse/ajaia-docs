import os

# Must run before `app` is imported: tests always use in-memory SQLite, never the real database.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SEED_PASSWORD"] = "test-password"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts from the same seeded database: users 1-3 (alice, bob, carol),
    doc 1 "Welcome" (alice owns; bob editor, carol viewer), doc 2 "Bob's notes" (bob owns; alice editor)."""
    from app import db
    from app.seed import seed_if_empty
    db.metadata.drop_all(db.engine)
    db.init_db()
    seed_if_empty()


@pytest.fixture
def login_as():
    """login_as("bob") returns a separate client already signed in as bob (own cookie jar)."""
    from app.main import app

    def make(name):
        client = TestClient(app)
        r = client.post("/api/login", json={"email": f"{name}@example.com", "password": "test-password"})
        assert r.status_code == 200
        return client
    return make
