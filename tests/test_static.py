from fastapi.testclient import TestClient

from app.main import app


def test_home_page_and_assets_are_served():
    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200 and "text/html" in home.headers["content-type"]
    assert '<main id="app">' in home.text
    for path in ("/static/style.css", "/static/app.js", "/static/vendor/quill.js", "/static/vendor/quill.snow.css"):
        assert client.get(path).status_code == 200, path


def test_pages_carry_security_headers():
    r = TestClient(app).get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "script-src" in r.headers["content-security-policy"] or "default-src 'self'" in r.headers["content-security-policy"]


def test_frontend_never_writes_server_data_as_html():
    # The one rule that keeps hostile titles and previews from running as script.
    js = open("static/app.js").read()
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js
