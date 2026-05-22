import io
from fastapi.testclient import TestClient
from backend.app import app

KEY = {"x-docs-key": "test-api-key"}


def _client():
    return TestClient(app)


def test_health_open():
    assert _client().get("/health").json() == {"ok": True}


def test_publish_requires_key():
    c = _client()
    r = c.post("/api/publish", data={"slug": "a/b", "title": "T", "from": "analyst"},
               files={"file": ("d.html", b"<h1>x</h1>", "text/html")})
    assert r.status_code == 401


def test_publish_then_read_roundtrip():
    c = _client()
    r = c.post("/api/publish",
               data={"slug": "analyst/demo", "title": "Demo", "tags": "x,y",
                     "project": "p", "from": "analyst"},
               files={"file": ("d.html", b"<h1>hello</h1>", "text/html")},
               headers=KEY)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1
    # agent read
    got = c.get("/api/doc/analyst/demo", headers=KEY)
    assert got.status_code == 200
    assert got.content == b"<h1>hello</h1>"
    # browser render
    rendered = c.get("/d/analyst/demo", headers=KEY)
    assert rendered.content == b"<h1>hello</h1>"


def test_republish_and_version_history():
    c = _client()
    for body in (b"<h1>1</h1>", b"<h1>2</h1>"):
        c.post("/api/publish",
               data={"slug": "analyst/v", "title": "V", "from": "analyst"},
               files={"file": ("d.html", body, "text/html")}, headers=KEY)
    assert c.get("/d/analyst/v", headers=KEY).content == b"<h1>2</h1>"
    assert c.get("/d/analyst/v/v1", headers=KEY).content == b"<h1>1</h1>"
    vs = c.get("/api/versions/analyst/v", headers=KEY).json()
    assert [v["version"] for v in vs["versions"]] == [2, 1]


def test_no_auth_redirects_to_login():
    c = _client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_bad_login_rejected():
    c = _client()
    r = c.post("/login", data={"user_id": "999999999", "password": "nope"},
               follow_redirects=False)
    assert r.status_code == 401
