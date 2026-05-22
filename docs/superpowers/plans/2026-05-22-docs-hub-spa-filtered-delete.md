# docs-hub SPA Wiring + Filtered Delete — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the server-rendered docs-hub index with the `docs.zip` SPA wired to live `/api/*` data, and add a safe filtered bulk-delete endpoint.

**Architecture:** The hash-routed SPA moves into `public/`, is mounted via `StaticFiles`, and fetches live data instead of the mock `data.js`. A new `POST /api/delete` selects whole docs by an AND-combined filter set and runs a mandatory dry-run → HMAC-confirm-token handshake before deleting rows, versions, and blobs.

**Tech Stack:** Python 3.13, FastAPI, Starlette, psycopg3 / Postgres, pytest, vanilla-JS SPA.

**Spec:** `docs/superpowers/specs/2026-05-22-docs-hub-spa-filtered-delete-design.html`

**Commit convention:** Every commit carries a `Co-Authored-By:` trailer naming the agent that authored it (per repo `AGENTS.md`). The `git commit` commands below omit the trailer for brevity — the executing agent appends its own.

**Run tests with:** `.venv/bin/pytest -v` (a clean `docs_test` DB + temp blob store are built by `tests/conftest.py`).

---

## Task 1: `storage.delete_doc` — remove a doc's blob directory

**Files:**
- Modify: `backend/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
def test_delete_doc_removes_dir():
    storage.store_blob("analyst/del", 1, b"<h1>x</h1>")
    storage.store_blob("analyst/del", 2, b"<h1>y</h1>")
    root = os.path.join(os.environ["STORE_ROOT"], "analyst", "del")
    assert os.path.isdir(root)
    storage.delete_doc("analyst/del")
    assert not os.path.exists(root)


def test_delete_doc_missing_is_noop():
    storage.delete_doc("analyst/never-stored")  # must not raise


def test_delete_doc_rejects_bad_slug():
    with pytest.raises(ValueError):
        storage.delete_doc("../evil")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_storage.py -v -k delete_doc`
Expected: FAIL — `AttributeError: module 'backend.storage' has no attribute 'delete_doc'`

- [ ] **Step 3: Write the implementation**

In `backend/storage.py`, add `import shutil` to the imports block (alongside `import hashlib`, `import os`, `import re`), then add this function at the end of the file:

```python
def delete_doc(slug: str) -> None:
    """Remove the blob directory for a slug. No-op if it does not exist."""
    if not is_valid_slug(slug):
        raise ValueError(f"invalid slug: {slug!r}")
    path = os.path.join(_store_root(), slug)
    shutil.rmtree(path, ignore_errors=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_storage.py -v`
Expected: PASS (all storage tests)

- [ ] **Step 5: Commit**

```bash
git add backend/storage.py tests/test_storage.py
git commit -m "feat: storage.delete_doc removes a doc's blob directory"
```

---

## Task 2: `list_docs` returns `byte_size` of the latest version

**Files:**
- Modify: `backend/docs_repo.py` (the `list_docs` function)
- Test: `tests/test_docs_repo.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_docs_repo.py`:

```python
def test_list_docs_includes_byte_size():
    body = b"<h1>sized body</h1>"
    docs_repo.publish("a/sz", "Sized", [], None, "analyst", body)
    d = docs_repo.list_docs()[0]
    assert d["byte_size"] == len(body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_docs_repo.py::test_list_docs_includes_byte_size -v`
Expected: FAIL — `KeyError: 'byte_size'`

- [ ] **Step 3: Modify `list_docs`**

In `backend/docs_repo.py`, replace the entire `list_docs` function with:

```python
def list_docs(project: str | None = None, agent: str | None = None) -> list[dict]:
    """Newest-updated first. `agent` filters by the poster of the latest version."""
    sql = (
        "SELECT d.slug, d.title, d.tags, d.project, d.updated_at, "
        "d.latest_version, v.posted_by, v.byte_size "
        "FROM docs d JOIN doc_versions v "
        "ON v.doc_id=d.id AND v.version=d.latest_version"
    )
    clauses, params = [], []
    if project is not None:
        clauses.append("d.project=%s")
        params.append(project)
    if agent is not None:
        clauses.append("v.posted_by=%s")
        params.append(agent)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY d.updated_at DESC"
    with db.docs_conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [
        {"slug": r[0], "title": r[1], "tags": r[2], "project": r[3],
         "updated_at": r[4], "latest_version": r[5], "posted_by": r[6],
         "byte_size": r[7]}
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_docs_repo.py -v`
Expected: PASS (all docs_repo tests)

- [ ] **Step 5: Commit**

```bash
git add backend/docs_repo.py tests/test_docs_repo.py
git commit -m "feat: list_docs returns latest-version byte_size"
```

---

## Task 3: `docs_repo.find_docs` — filtered doc lookup

**Files:**
- Modify: `backend/docs_repo.py`
- Test: `tests/test_docs_repo.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docs_repo.py`:

```python
def test_find_docs_by_each_filter():
    docs_repo.publish("a/one", "Alpha One", ["x"], "alpha", "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/two", "Beta Two", ["y"], "beta", "kimi", b"<h1>2</h1>")
    assert [d["slug"] for d in docs_repo.find_docs({"slug": "a/one"})] == ["a/one"]
    assert [d["slug"] for d in docs_repo.find_docs({"project": "alpha"})] == ["a/one"]
    assert [d["slug"] for d in docs_repo.find_docs({"author": "kimi"})] == ["a/two"]
    assert [d["slug"] for d in docs_repo.find_docs({"tag": "x"})] == ["a/one"]
    assert [d["slug"] for d in docs_repo.find_docs({"q": "beta"})] == ["a/two"]
    assert {d["slug"] for d in docs_repo.find_docs({})} == {"a/one", "a/two"}


def test_find_docs_and_combines():
    docs_repo.publish("a/one", "Alpha One", [], "alpha", "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/two", "Alpha Two", [], "alpha", "kimi", b"<h1>2</h1>")
    res = docs_repo.find_docs({"project": "alpha", "author": "kimi"})
    assert [d["slug"] for d in res] == ["a/two"]


def test_find_docs_shape():
    docs_repo.publish("a/one", "Alpha One", [], "alpha", "analyst", b"<h1>1</h1>")
    d = docs_repo.find_docs({"project": "alpha"})[0]
    assert set(d) == {"slug", "title", "latest_version"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_docs_repo.py -v -k find_docs`
Expected: FAIL — `AttributeError: module 'backend.docs_repo' has no attribute 'find_docs'`

- [ ] **Step 3: Write the implementation**

In `backend/docs_repo.py`, add this function after `list_docs`:

```python
def find_docs(filters: dict) -> list[dict]:
    """Docs matching the AND-combined filter set. Returns
    [{slug, title, latest_version}], newest-updated first.

    Recognised filter keys (all optional): slug, project, author, tag, q,
    updated_before, updated_after.
    """
    sql = (
        "SELECT d.slug, d.title, d.latest_version "
        "FROM docs d JOIN doc_versions v "
        "ON v.doc_id=d.id AND v.version=d.latest_version"
    )
    clauses, params = [], []
    if filters.get("slug"):
        clauses.append("d.slug=%s")
        params.append(filters["slug"])
    if filters.get("project"):
        clauses.append("d.project=%s")
        params.append(filters["project"])
    if filters.get("author"):
        clauses.append("v.posted_by=%s")
        params.append(filters["author"])
    if filters.get("tag"):
        clauses.append("%s = ANY(d.tags)")
        params.append(filters["tag"])
    if filters.get("q"):
        clauses.append("(d.title ILIKE %s OR d.slug ILIKE %s)")
        like = f"%{filters['q']}%"
        params += [like, like]
    if filters.get("updated_before"):
        clauses.append("d.updated_at < %s")
        params.append(filters["updated_before"])
    if filters.get("updated_after"):
        clauses.append("d.updated_at > %s")
        params.append(filters["updated_after"])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY d.updated_at DESC"
    with db.docs_conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [{"slug": r[0], "title": r[1], "latest_version": r[2]} for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_docs_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/docs_repo.py tests/test_docs_repo.py
git commit -m "feat: docs_repo.find_docs filtered lookup"
```

---

## Task 4: `docs_repo.delete_docs` — delete rows, versions, blobs

**Files:**
- Modify: `backend/docs_repo.py`
- Test: `tests/test_docs_repo.py`

- [ ] **Step 1: Write the failing tests**

Add `import os` to the imports at the top of `tests/test_docs_repo.py` (it currently imports only `pytest` and `docs_repo`), then append:

```python
def test_delete_docs_removes_rows_versions_blobs():
    docs_repo.publish("a/del", "Del", [], None, "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/del", "Del", [], None, "analyst", b"<h1>2</h1>")
    n = docs_repo.delete_docs(["a/del"])
    assert n == 1
    assert docs_repo.get_latest("a/del") is None
    assert docs_repo.list_versions("a/del") == []
    blob_dir = os.path.join(os.environ["STORE_ROOT"], "a", "del")
    assert not os.path.exists(blob_dir)


def test_delete_docs_unknown_slug_counts_zero():
    assert docs_repo.delete_docs(["nope/nope"]) == 0


def test_delete_docs_partial_set():
    docs_repo.publish("a/keep", "Keep", [], None, "analyst", b"<h1>k</h1>")
    docs_repo.publish("a/drop", "Drop", [], None, "analyst", b"<h1>d</h1>")
    assert docs_repo.delete_docs(["a/drop", "missing/x"]) == 1
    assert docs_repo.get_latest("a/keep") is not None
    assert docs_repo.get_latest("a/drop") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_docs_repo.py -v -k delete_docs`
Expected: FAIL — `AttributeError: module 'backend.docs_repo' has no attribute 'delete_docs'`

- [ ] **Step 3: Write the implementation**

In `backend/docs_repo.py`, add this function after `find_docs`:

```python
def delete_docs(slugs: list[str]) -> int:
    """Delete the named docs (versions cascade via the doc_versions FK) and
    their blob directories. Returns the count of doc rows actually deleted.
    The DB delete commits before blob removal, so a crash leaves orphan
    blobs (harmless) rather than orphan rows."""
    deleted = 0
    for slug in slugs:
        with db.docs_conn() as c:
            row = c.execute("DELETE FROM docs WHERE slug=%s RETURNING id",
                            (slug,)).fetchone()
            c.commit()
        if row is not None:
            deleted += 1
            storage.delete_doc(slug)
    return deleted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_docs_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/docs_repo.py tests/test_docs_repo.py
git commit -m "feat: docs_repo.delete_docs removes rows, versions and blobs"
```

---

## Task 5: Delete confirm-token helpers in `session.py`

**Files:**
- Modify: `backend/session.py`
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session.py`:

```python
def test_delete_token_roundtrip():
    f = {"project": "analyst"}
    tok = session.make_delete_token(f)
    assert session.verify_delete_token(tok, f) is True


def test_delete_token_filter_order_insensitive():
    tok = session.make_delete_token({"project": "p", "author": "a"})
    assert session.verify_delete_token(tok, {"author": "a", "project": "p"}) is True


def test_delete_token_rejects_changed_filters():
    tok = session.make_delete_token({"project": "alpha"})
    assert session.verify_delete_token(tok, {"project": "beta"}) is False


def test_delete_token_rejects_tampered():
    tok = session.make_delete_token({"project": "p"})
    bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    assert session.verify_delete_token(bad, {"project": "p"}) is False


def test_delete_token_rejects_garbage():
    assert session.verify_delete_token("not-a-token", {"project": "p"}) is False


def test_delete_token_rejects_expired(monkeypatch):
    old = int(time.time()) - session.DELETE_TOKEN_TTL - 10
    monkeypatch.setattr(time, "time", lambda: old)
    tok = session.make_delete_token({"project": "p"})
    monkeypatch.undo()
    assert session.verify_delete_token(tok, {"project": "p"}) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_session.py -v -k delete_token`
Expected: FAIL — `AttributeError: module 'backend.session' has no attribute 'make_delete_token'`

- [ ] **Step 3: Write the implementation**

In `backend/session.py`, add this block at the end of the file:

```python
DELETE_TOKEN_TTL = 300  # seconds — a confirm token is good for 5 minutes


def _canonical_filters(filters: dict) -> str:
    """Stable string for the active (non-empty) filter values, sorted by key.
    `confirm_token` is excluded so a confirm request body produces the same
    canonical form as its preview request."""
    items = sorted(
        (k, str(v).strip())
        for k, v in filters.items()
        if k != "confirm_token" and str(v).strip()
    )
    return "&".join(f"{k}={v}" for k, v in items)


def make_delete_token(filters: dict) -> str:
    """HMAC token binding a delete to its exact filter set, format
    <issued_at>.<hmac>."""
    issued_at = int(time.time())
    payload = f"{issued_at}.{_canonical_filters(filters)}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{issued_at}.{sig}"


def verify_delete_token(token: str, filters: dict) -> bool:
    """True iff `token` was minted for this filter set within the TTL."""
    parts = token.split(".")
    if len(parts) != 2:
        return False
    raw_ts, sig = parts
    try:
        issued_at = int(raw_ts)
    except ValueError:
        return False
    now = int(time.time())
    if issued_at > now + 60 or now - issued_at > DELETE_TOKEN_TTL:
        return False
    payload = f"{issued_at}.{_canonical_filters(filters)}"
    expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/session.py tests/test_session.py
git commit -m "feat: HMAC delete confirm-token mint/verify"
```

---

## Task 6: `POST /api/delete` + `GET /api/whoami`

**Files:**
- Modify: `backend/api.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_app.py`, change the top imports from `from fastapi.testclient import TestClient` / `from backend.app import app` to also import the backend modules — the import block becomes:

```python
import io
from fastapi.testclient import TestClient
from backend.app import app
from backend import docs_repo, session

KEY = {"x-docs-key": "test-api-key"}
```

Then append this helper and the tests to `tests/test_app.py`:

```python
def _publish(c, slug, project="p", author="analyst", tags="", body=b"<h1>x</h1>"):
    return c.post("/api/publish",
                  data={"slug": slug, "title": slug, "tags": tags,
                        "project": project, "from": author},
                  files={"file": ("d.html", body, "text/html")}, headers=KEY)


def test_delete_requires_a_filter():
    r = _client().post("/api/delete", json={}, headers=KEY)
    assert r.status_code == 400


def test_delete_requires_auth():
    r = _client().post("/api/delete", json={"project": "analyst"})
    assert r.status_code == 401


def test_delete_preview_then_confirm():
    c = _client()
    _publish(c, "analyst/d1", project="analyst")
    _publish(c, "analyst/d2", project="analyst")
    prev = c.post("/api/delete", json={"project": "analyst"}, headers=KEY)
    assert prev.status_code == 200, prev.text
    pj = prev.json()
    assert pj["preview"] is True and pj["count"] == 2
    assert docs_repo.get_latest("analyst/d1") is not None  # preview deletes nothing
    conf = c.post("/api/delete",
                  json={"project": "analyst", "confirm_token": pj["confirm_token"]},
                  headers=KEY)
    assert conf.status_code == 200, conf.text
    cj = conf.json()
    assert cj["preview"] is False and cj["deleted"] == 2
    assert docs_repo.get_latest("analyst/d1") is None


def test_delete_bad_token_rejected():
    c = _client()
    _publish(c, "analyst/d1", project="analyst")
    r = c.post("/api/delete",
               json={"project": "analyst", "confirm_token": "1.deadbeef"},
               headers=KEY)
    assert r.status_code == 409
    assert docs_repo.get_latest("analyst/d1") is not None


def test_delete_token_bound_to_filters():
    c = _client()
    _publish(c, "analyst/d1", project="analyst")
    _publish(c, "beta/d2", project="beta")
    prev = c.post("/api/delete", json={"project": "analyst"}, headers=KEY)
    token = prev.json()["confirm_token"]
    # token from project=analyst must not confirm a project=beta delete
    r = c.post("/api/delete",
               json={"project": "beta", "confirm_token": token}, headers=KEY)
    assert r.status_code == 409


def test_delete_accepts_human_cookie():
    c = _client()
    _publish(c, "analyst/d1", project="analyst")
    c.cookies.set("session", session.make_session_token(1))
    r = c.post("/api/delete", json={"project": "analyst"})
    assert r.status_code == 200
    assert r.json()["preview"] is True


def test_whoami_agent():
    r = _client().get("/api/whoami", headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["principal"] == "agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_app.py -v -k "delete or whoami"`
Expected: FAIL — `/api/delete` and `/api/whoami` return 404 (routes not defined)

- [ ] **Step 3: Write the implementation**

In `backend/api.py`, change the FastAPI import line to include `Body`:

```python
from fastapi import APIRouter, Body, Form, Request, UploadFile
```

Add `session` to the existing backend import line so it reads:

```python
from backend import docs_repo, session
```

Then append these two routes to the end of `backend/api.py`:

```python
_FILTER_KEYS = ("slug", "project", "author", "tag", "q",
                "updated_before", "updated_after")


@router.post("/delete")
async def delete(request: Request,
                 body: dict = Body(default={})) -> JSONResponse:
    """Delete whole docs by filter. Two-step: a call with no `confirm_token`
    previews and returns a token; a call echoing a valid token executes.
    Accepts the agent API key or a human session cookie (the middleware has
    already admitted one of the two)."""
    filters = {
        k: str(body[k]).strip()
        for k in _FILTER_KEYS
        if body.get(k) is not None and str(body[k]).strip()
    }
    if not filters:
        return JSONResponse({"ok": False, "error": "at least one filter required"},
                            status_code=400)
    matched = docs_repo.find_docs(filters)
    token = body.get("confirm_token")
    if not token:
        return JSONResponse({
            "ok": True, "preview": True, "count": len(matched),
            "matched": matched,
            "confirm_token": session.make_delete_token(filters),
        })
    if not session.verify_delete_token(str(token), filters):
        return JSONResponse(
            {"ok": False, "error": "confirm token invalid or expired"},
            status_code=409)
    deleted = docs_repo.delete_docs([m["slug"] for m in matched])
    return JSONResponse({"ok": True, "preview": False, "deleted": deleted})


@router.get("/whoami")
async def whoami(request: Request) -> JSONResponse:
    """Identify the current principal for the SPA top bar."""
    return JSONResponse({
        "ok": True,
        "principal": request.state.principal,
        "user_id": request.state.user_id,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: PASS (all app tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add backend/api.py tests/test_app.py
git commit -m "feat: POST /api/delete (filtered, two-step) and GET /api/whoami"
```

---

## Task 7: Apply `docs.zip` into `public/`

**Files:**
- Create: `public/index.html`, `public/app.js`, `public/styles.css` (extracted from `docs.zip`)
- Delete: `docs.zip`

This task places the SPA files. `app.js` is rewired to live data in Task 9; between this task and Task 9 the SPA is not yet functional, which is expected.

- [ ] **Step 1: Extract the archive into `public/`**

Run from the repo root:

```bash
unzip -o docs.zip -d public/
mv "public/Docs Hub.html" public/index.html
rm public/data.js
ls public/
```

Expected `ls` output: `app.js  index.html  styles.css`

- [ ] **Step 2: Remove the `data.js` script tag from `public/index.html`**

In `public/index.html`, delete this line (it loads the now-removed mock data file):

```html
  <script src="data.js"></script>
```

Leave the `<script src="app.js"></script>` line and everything else intact.

- [ ] **Step 3: Delete the archive**

```bash
rm docs.zip
```

- [ ] **Step 4: Verify**

Run: `git status --short`
Expected: `docs.zip` no longer listed; `public/index.html`, `public/app.js`, `public/styles.css` shown as new files.

- [ ] **Step 5: Commit**

```bash
git add public/ docs.zip
git commit -m "feat: apply docs.zip SPA files into public/"
```

(`git add docs.zip` stages its deletion.)

---

## Task 8: Mount the SPA; drop the server-rendered index

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/views.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_root_serves_spa_when_authed():
    c = _client()
    c.cookies.set("session", session.make_session_token(1))
    r = c.get("/")
    assert r.status_code == 200
    assert '<div id="app"' in r.text


def test_static_assets_served_when_authed():
    c = _client()
    c.cookies.set("session", session.make_session_token(1))
    assert c.get("/app.js").status_code == 200
    assert c.get("/styles.css").status_code == 200


def test_doc_render_still_works():
    c = _client()
    _publish(c, "analyst/r1")
    assert c.get("/d/analyst/r1", headers=KEY).content == b"<h1>x</h1>"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_app.py -v -k "spa or static_assets"`
Expected: FAIL — `/` returns the old server-rendered table (no `<div id="app"`) and `/app.js` returns 404.

- [ ] **Step 3: Remove the server-rendered index from `views.py`**

In `backend/views.py`, delete the `import html as _html` line, delete the entire `_INDEX_HEAD = """..."""` string constant, and delete the entire `index()` function (the `@router.get("/")` route). Keep `render_version` and `render_latest`. The file's imports become:

```python
"""Browser-facing routes: per-version artifact rendering for the SPA iframe."""
from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import HTMLResponse, Response

from backend import docs_repo

router = APIRouter()
```

- [ ] **Step 4: Mount `StaticFiles` in `app.py`**

In `backend/app.py`, add the import:

```python
from fastapi.staticfiles import StaticFiles
```

Then, after the `app.include_router(views.router)` line and before the `@app.get("/health")` block, add:

```python
_PUBLIC_DIR = _REPO_ROOT / "public"
```

And as the **last** statement in the file (after the `health()` function), add the catch-all mount:

```python
app.mount("/", StaticFiles(directory=str(_PUBLIC_DIR), html=True), name="spa")
```

The mount is added last so the `/api/*`, `/d/*`, `/login`, `/logout`, `/health` routes resolve first; everything else (the SPA shell and its assets) falls through to `StaticFiles`. `html=True` makes `GET /` serve `public/index.html`. The existing `auth_middleware` still runs first, so an unauthenticated `GET /` is redirected to `/login` before `StaticFiles` is reached.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: PASS — including the pre-existing `test_no_auth_redirects_to_login` (unauthenticated `/` still redirects).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/views.py tests/test_app.py
git commit -m "feat: mount the SPA at / and drop the server-rendered index"
```

---

## Task 9: Rewire `app.js` to live backend data

**Files:**
- Modify: `backend/public/app.js` → fully replaced

This is a frontend-only change with no pytest coverage; it is verified by the end-to-end smoke test in Task 10. The rewire swaps the mock `window.DOCS` / `window.VERSIONS` / `window.SAMPLE_ARTIFACT` reads for `fetch()` calls to `/api/list`, `/api/versions/<slug>`, and `/api/whoami`, points the doc-viewer iframe at the server `/d/<slug>/v<n>` render route, and removes the now-dead in-SPA login screen (auth is handled by the server `/login` page).

- [ ] **Step 1: Replace the entire contents of `public/app.js` with:**

```javascript
// docs-hub SPA — hash-routed screens, live backend data.
// Routes:
//   #/                  → index
//   #/d/<slug>          → doc viewer (chrome + iframe)
//   #/d/<slug>/v<n>     → doc viewer at specific version
//   #/d/<slug>/versions → version history

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ─────────────────────────── data layer ───────────────────────────

let _docs = null;        // cached GET /api/list
const _versions = {};    // slug → GET /api/versions/<slug>
let _whoami = null;      // cached GET /api/whoami

async function fetchJSON(url) {
  const r = await fetch(url, { headers: { accept: 'application/json' } });
  if (!r.ok) throw new Error(url + ' → ' + r.status);
  return r.json();
}

async function loadDocs() {
  if (_docs === null) {
    const j = await fetchJSON('/api/list');
    _docs = j.docs || [];
  }
  return _docs;
}

async function loadVersions(slug) {
  if (!(slug in _versions)) {
    try {
      const j = await fetchJSON('/api/versions/' + slug);
      _versions[slug] = j.versions || [];
    } catch (e) {
      _versions[slug] = [];
    }
  }
  return _versions[slug];
}

async function loadWhoami() {
  if (_whoami === null) {
    try { _whoami = await fetchJSON('/api/whoami'); }
    catch (e) { _whoami = { user_id: null }; }
  }
  return _whoami;
}

// ─────────────────────────── utilities ───────────────────────────

function fmtBytes(n) {
  if (n < 1024) return n + ' b';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' kb';
  return (n / (1024 * 1024)).toFixed(2) + ' mb';
}

function relTime(iso) {
  const t = new Date(iso).getTime();
  const now = Date.now();
  const d = Math.max(0, now - t);
  const mins = d / 60_000;
  if (mins < 1) return 'just now';
  if (mins < 60) return Math.round(mins) + 'm ago';
  const hours = mins / 60;
  if (hours < 24) return Math.round(hours) + 'h ago';
  const days = hours / 24;
  if (days < 14) return Math.round(days) + 'd ago';
  if (days < 60) return Math.round(days / 7) + 'w ago';
  return Math.round(days / 30) + 'mo ago';
}

function absTime(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()) +
    ' ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes())
  );
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

function uniq(arr) { return [...new Set(arr)]; }

// ─────────────────────────── filter state ───────────────────────────

const FILTER = {
  q: '', project: '', agent: '', tag: '',
  sort: 'updated', sortDir: 'desc',
};

const SORT_DEFAULT_DIR = {
  title: 'asc', slug: 'asc', project: 'asc', tags: 'desc',
  agent: 'asc', updated: 'desc', version: 'desc', size: 'desc',
};

function setSort(key) {
  if (FILTER.sort === key) {
    FILTER.sortDir = FILTER.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    FILTER.sort = key;
    FILTER.sortDir = SORT_DEFAULT_DIR[key] || 'desc';
  }
}

function applyFilters(docs) {
  let out = docs.slice();
  if (FILTER.q) {
    const q = FILTER.q.toLowerCase();
    out = out.filter(
      (d) => d.title.toLowerCase().includes(q) || d.slug.toLowerCase().includes(q),
    );
  }
  if (FILTER.project) out = out.filter((d) => d.project === FILTER.project);
  if (FILTER.agent)   out = out.filter((d) => d.posted_by === FILTER.agent);
  if (FILTER.tag)     out = out.filter((d) => d.tags.includes(FILTER.tag));

  const dir = FILTER.sortDir === 'asc' ? 1 : -1;
  const sizeOf = (d) => d.byte_size ?? 0;
  const cmp = {
    title:   (a, b) => a.title.localeCompare(b.title),
    slug:    (a, b) => a.slug.localeCompare(b.slug),
    project: (a, b) => (a.project || '').localeCompare(b.project || ''),
    tags:    (a, b) => a.tags.length - b.tags.length,
    agent:   (a, b) => a.posted_by.localeCompare(b.posted_by),
    updated: (a, b) => new Date(a.updated_at) - new Date(b.updated_at),
    version: (a, b) => a.latest_version - b.latest_version,
    size:    (a, b) => sizeOf(a) - sizeOf(b),
  }[FILTER.sort] || (() => 0);
  out.sort((a, b) => dir * cmp(a, b));
  return out;
}

// ─────────────────────────── screens ───────────────────────────

function renderTopbar(opts = {}) {
  const crumbs = opts.crumbs || [];
  const crumbHtml = crumbs.length
    ? crumbs
        .map((c, i) => {
          const piece = c.href
            ? `<a href="${esc(c.href)}">${esc(c.label)}</a>`
            : `<span class="here">${esc(c.label)}</span>`;
          return (i ? '<span class="sep">/</span>' : '') + piece;
        })
        .join('')
    : '';
  const who = esc(_whoami && _whoami.user_id != null ? _whoami.user_id : '—');
  return `
    <header class="topbar">
      <a href="#/" class="brand" style="color:inherit">
        <span class="prompt">$</span>
        <span class="host">docs.nitjsefni.eu</span>
        <span class="cursor"></span>
      </a>
      <div class="crumbs">${crumbHtml}</div>
      <div class="meta">
        <span>user <span class="who">${who}</span></span>
        <span class="dot">·</span>
        <a href="/logout" title="Sign out">logout</a>
      </div>
    </header>
  `;
}

function renderIndex() {
  const docs = applyFilters(_docs);
  const total = _docs.length;
  const allProjects = uniq(_docs.map((d) => d.project).filter(Boolean)).sort();
  const allAgents   = uniq(_docs.map((d) => d.posted_by)).sort();
  const allTags     = uniq(_docs.flatMap((d) => d.tags)).sort();

  const opt = (val, label, sel) =>
    `<option value="${esc(val)}" ${val === sel ? 'selected' : ''}>${esc(label)}</option>`;

  const headers = [
    { key: 'title',   label: 'Title / Slug' },
    { key: 'project', label: 'Project' },
    { key: 'tags',    label: 'Tags' },
    { key: 'agent',   label: 'Agent' },
    { key: 'updated', label: 'Updated' },
    { key: 'version', label: 'Ver' },
    { key: 'size',    label: 'Size', align: 'right' },
  ];

  const headHtml = headers
    .map((h) => {
      const active = FILTER.sort === h.key;
      const glyph = active ? (FILTER.sortDir === 'asc' ? '▲' : '▼') : '▼';
      const cls = active ? '' : 'inactive';
      const style = h.align === 'right' ? 'text-align:right' : '';
      const titleAttr = active
        ? `title="sort by ${h.label.toLowerCase()} — reverse"`
        : `title="sort by ${h.label.toLowerCase()}"`;
      return `<th class="${cls}" style="${style}" ${titleAttr} data-sort="${h.key}">${esc(h.label)}<span class="arrow">${glyph}</span></th>`;
    })
    .join('');

  const rowHtml = docs.length
    ? docs
        .map((d) => {
          const size = d.byte_size ? fmtBytes(d.byte_size) : '';
          return `
            <tr>
              <td class="title-cell">
                <a class="t" href="#/d/${esc(d.slug)}">${esc(d.title)}</a>
                <div class="slug"><span class="prompt">›</span>${esc(d.slug)}</div>
              </td>
              <td class="proj">${esc(d.project || '—')}</td>
              <td class="tags">${d.tags.map((t) => `<span class="tag" data-tag="${esc(t)}">${esc(t)}</span>`).join('')}</td>
              <td class="agent">${esc(d.posted_by)}</td>
              <td class="upd">
                <span class="rel">${relTime(d.updated_at)}</span>
                <span class="abs">${absTime(d.updated_at)}</span>
              </td>
              <td class="ver">
                <a class="v" href="#/d/${esc(d.slug)}">v${d.latest_version}</a>
                <a class="hist" href="#/d/${esc(d.slug)}/versions" title="version history">log →</a>
              </td>
              <td class="size tnum">${size}</td>
            </tr>
          `;
        })
        .join('')
    : `<tr class="empty"><td colspan="${headers.length}">no docs match these filters · <a href="#" id="clear-filters">clear all</a></td></tr>`;

  return `
    ${renderTopbar({ crumbs: [{ label: 'index' }] })}
    <main class="main">
      <div class="filterbar">
        <div class="field">
          <span class="label">search</span>
          <input id="f-q" placeholder="title or slug…" value="${esc(FILTER.q)}" autocomplete="off">
        </div>
        <div class="field select">
          <span class="label">project</span>
          <select id="f-project">
            <option value="">all</option>
            ${allProjects.map((p) => opt(p, p, FILTER.project)).join('')}
          </select>
        </div>
        <div class="field select">
          <span class="label">agent</span>
          <select id="f-agent">
            <option value="">all</option>
            ${allAgents.map((a) => opt(a, a, FILTER.agent)).join('')}
          </select>
        </div>
        <div class="field select">
          <span class="label">tag</span>
          <select id="f-tag">
            <option value="">all</option>
            ${allTags.map((t) => opt(t, '#' + t, FILTER.tag)).join('')}
          </select>
        </div>
        <div class="count"><b class="accent">${docs.length}</b> / ${total} docs</div>
      </div>
      <table class="docs-table">
        <thead><tr>${headHtml}</tr></thead>
        <tbody>${rowHtml}</tbody>
      </table>
    </main>
  `;
}

function wireIndex() {
  const reroute = () => render();
  $('#f-q')?.addEventListener('input', (e) => { FILTER.q = e.target.value; reroute(); });
  $('#f-project')?.addEventListener('change', (e) => { FILTER.project = e.target.value; reroute(); });
  $('#f-agent')?.addEventListener('change', (e) => { FILTER.agent = e.target.value; reroute(); });
  $('#f-tag')?.addEventListener('change', (e) => { FILTER.tag = e.target.value; reroute(); });
  $$('[data-sort]').forEach((th) =>
    th.addEventListener('click', () => {
      setSort(th.dataset.sort);
      reroute();
    }),
  );
  $$('.docs-table .tag[data-tag]').forEach((el) =>
    el.addEventListener('click', () => {
      FILTER.tag = FILTER.tag === el.dataset.tag ? '' : el.dataset.tag;
      reroute();
    }),
  );
  $('#clear-filters')?.addEventListener('click', (e) => {
    e.preventDefault();
    Object.assign(FILTER, { q: '', project: '', agent: '', tag: '' });
    reroute();
  });
  if (FILTER.q) {
    const inp = $('#f-q');
    if (inp) {
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);
    }
  }
}

function renderDocViewer(slug, requestedVersion) {
  const doc = (_docs || []).find((d) => d.slug === slug);
  if (!doc) return renderNotFound('/d/' + slug);

  const versions = _versions[slug] || [];
  const latest = doc.latest_version;
  const ver = requestedVersion ?? latest;
  const v = versions.find((x) => x.version === ver);
  if (!v) return renderNotFound('/d/' + slug + '/v' + ver);

  const isStale = ver !== latest;
  const idx = versions.findIndex((x) => x.version === ver);
  const newer = versions[idx - 1];
  const older = versions[idx + 1];

  const crumbs = [
    { label: 'index', href: '#/' },
    { label: doc.project || '—' },
    { label: slug.split('/').slice(1).join('/') || slug, href: '#/d/' + slug },
  ];

  return `
    ${renderTopbar({ crumbs })}
    <div class="docview">
      <div class="docchrome">
        <div class="left">
          <div class="title-row">
            <div class="title">${esc(doc.title)}</div>
            <div class="vtag ${isStale ? 'stale stale-warn' : ''}">v${v.version}</div>
          </div>
          <div class="meta">
            <span class="slug"><span class="prompt">›</span>${esc(slug)}</span>
            <span class="dot">·</span>
            <span>by <span class="agent">${esc(v.posted_by)}</span></span>
            <span class="dot">·</span>
            <span>${relTime(v.created_at)} · ${absTime(v.created_at)}</span>
            <span class="dot">·</span>
            <span>${fmtBytes(v.byte_size)}</span>
            <span class="dot">·</span>
            <span title="${esc(v.sha256)}">sha ${esc(v.sha256.slice(0, 10))}…</span>
          </div>
        </div>
        <div class="actions">
          <div class="nav-arrows">
            <button ${older ? `onclick="location.hash='#/d/${esc(slug)}/v${older.version}'"` : 'disabled'} title="older version">←</button>
            <span class="which">v${v.version} / v${latest}</span>
            <button ${newer ? `onclick="location.hash='#/d/${esc(slug)}/v${newer.version}'"` : 'disabled'} title="newer version">→</button>
          </div>
          ${isStale ? `<a class="btn accent" href="#/d/${esc(slug)}">latest →</a>` : ''}
          <a class="btn" href="#/d/${esc(slug)}/versions">log <span class="kbd">L</span></a>
          <button class="btn" id="copy-link" title="copy permalink">⎘ link</button>
        </div>
      </div>
      <div class="artifact-frame">
        <iframe id="artifact" sandbox="allow-same-origin" src="/d/${esc(slug)}/v${v.version}"></iframe>
      </div>
    </div>
  `;
}

function wireDocViewer() {
  $('#copy-link')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const url = location.href;
    if (navigator.clipboard) navigator.clipboard.writeText(url).catch(() => {});
    const old = btn.innerHTML;
    btn.innerHTML = '✓ copied';
    setTimeout(() => (btn.innerHTML = old), 1200);
  });
  document.addEventListener('keydown', _docKeydown);
}
const _docKeydown = (e) => {
  if (e.target.matches('input, textarea, select')) return;
  if (e.key === 'l' || e.key === 'L') {
    const m = location.hash.match(/^#\/d\/(.+?)(?:\/v\d+|\/versions)?$/);
    if (m) location.hash = '#/d/' + m[1] + '/versions';
  }
};

function renderVersions(slug) {
  const doc = (_docs || []).find((d) => d.slug === slug);
  if (!doc) return renderNotFound('/d/' + slug + '/versions');
  const versions = _versions[slug] || [];
  const latest = doc.latest_version;

  const crumbs = [
    { label: 'index', href: '#/' },
    { label: doc.project || '—' },
    { label: slug.split('/').slice(1).join('/') || slug, href: '#/d/' + slug },
    { label: 'versions' },
  ];

  const rows = versions
    .map(
      (v) => `
      <div class="version-row" data-href="#/d/${esc(slug)}/v${v.version}">
        <div class="vtag ${v.version === latest ? 'latest' : ''}">v${v.version}</div>
        <div>
          <div class="who">${esc(v.posted_by)}</div>
          <div class="sha" title="${esc(v.sha256)}">sha ${esc(v.sha256.slice(0, 16))}…</div>
        </div>
        <div class="when">
          ${relTime(v.created_at)}
          <span class="abs">${absTime(v.created_at)}</span>
        </div>
        <div class="size tnum">${fmtBytes(v.byte_size)}</div>
        <div class="sha tnum">${esc(v.sha256.slice(0, 8))}</div>
        <div class="actions">
          <button class="render-btn">render →</button>
        </div>
      </div>
    `,
    )
    .join('');

  return `
    ${renderTopbar({ crumbs })}
    <main class="main">
      <div class="version-head">
        <div>
          <h1>${esc(doc.title)}</h1>
          <div class="sub"><span class="prompt">›</span>${esc(slug)} · ${versions.length} version${versions.length === 1 ? '' : 's'}</div>
        </div>
        <div class="version-actions">
          <a class="btn" href="#/d/${esc(slug)}">view latest →</a>
          <a class="btn" href="#/">← back to index</a>
        </div>
      </div>
      <div class="version-list">${rows}</div>
    </main>
  `;
}

function wireVersions() {
  $$('.version-row').forEach((row) =>
    row.addEventListener('click', () => {
      location.hash = row.dataset.href;
    }),
  );
}

function renderNotFound(path) {
  return `
    ${renderTopbar({ crumbs: [{ label: '404' }] })}
    <div class="notfound">
      <div>
        <div class="code">4<span class="slash">/</span>4</div>
        <div class="path"><span class="prompt">›</span>${esc(path || location.hash.slice(1) || '/')}</div>
        <h2>No artifact under that slug.</h2>
        <p>The slug doesn't resolve to any published document, or that specific version doesn't exist yet. Re-publish from the agent CLI, or pick a different slug from the index.</p>
        <div class="actions">
          <a class="btn accent" href="#/">← back to index</a>
        </div>
      </div>
    </div>
  `;
}

function renderError(err) {
  return `
    ${renderTopbar({ crumbs: [{ label: 'error' }] })}
    <div class="notfound">
      <div>
        <div class="code">5<span class="slash">/</span>0<span class="slash">/</span>0</div>
        <h2>Couldn't load from the server.</h2>
        <p>${esc(String((err && err.message) || err))}</p>
        <div class="actions">
          <a class="btn accent" href="#/">← back to index</a>
        </div>
      </div>
    </div>
  `;
}

// ─────────────────────────── router ───────────────────────────

function parseRoute() {
  const h = location.hash.replace(/^#/, '') || '/';
  if (h === '/' || h === '') return { name: 'index' };
  if (h === '/404') return { name: '404' };
  let m = h.match(/^\/d\/(.+?)\/versions$/);
  if (m) return { name: 'versions', slug: m[1] };
  m = h.match(/^\/d\/(.+?)\/v(\d+)$/);
  if (m) return { name: 'viewer', slug: m[1], version: Number(m[2]) };
  m = h.match(/^\/d\/(.+)$/);
  if (m) return { name: 'viewer', slug: m[1], version: null };
  return { name: '404' };
}

async function render() {
  document.removeEventListener('keydown', _docKeydown);
  const route = parseRoute();
  const root = $('#app');
  let html = '';
  try {
    await loadWhoami();
    if (route.name === 'index') {
      await loadDocs();
      html = renderIndex();
    } else if (route.name === 'versions') {
      await loadDocs();
      await loadVersions(route.slug);
      html = renderVersions(route.slug);
    } else if (route.name === 'viewer') {
      await loadDocs();
      await loadVersions(route.slug);
      html = renderDocViewer(route.slug, route.version);
    } else {
      html = renderNotFound();
    }
  } catch (e) {
    html = renderError(e);
  }
  root.innerHTML = html;
  switch (route.name) {
    case 'index':    wireIndex(); break;
    case 'versions': wireVersions(); break;
    case 'viewer':   wireDocViewer(); break;
  }
  document.title =
    ({
      index: 'docs.nitjsefni.eu',
      versions: 'versions · docs',
      viewer: (route.slug || '') + ' · docs',
      '404': '404 · docs',
    })[route.name] || 'docs.nitjsefni.eu';
}

window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', render);
```

- [ ] **Step 2: Commit**

```bash
git add public/app.js
git commit -m "feat: rewire SPA app.js to live backend data"
```

---

## Task 10: End-to-end verification

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test green, no failures or errors.

- [ ] **Step 2: Confirm the archive is gone**

Run: `git status --short && ls`
Expected: `docs.zip` is not present in the directory listing and not in git status.

- [ ] **Step 3: Smoke-test the running server**

Start the app against the dev database (a `.env` with `DATABASE_URL_DOCS`, `DATABASE_URL_AUTH`, `STORE_ROOT`, `SESSION_SECRET`, `DOCS_HUB_API_KEY` is already present):

```bash
.venv/bin/uvicorn backend.app:app --port 8099 &
sleep 2
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8099/health
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8099/
```

Expected: `/health` → `200`; `/` → `302` (redirect to `/login`, since curl sends no session cookie). Stop the server afterward (`kill %1`).

- [ ] **Step 4: Browser check (manual)**

In a browser: open the site, sign in via the server `/login` page, confirm the SPA index lists real published docs with working search / project / agent / tag filters and column sorting; open a doc and confirm the artifact renders in the iframe; open version history. Then exercise delete: `POST /api/delete` with a filter (e.g. `{"project":"<something>"}`) using the API key, confirm the preview returns a `confirm_token` and a `matched` list, repeat the call with the token, and confirm the docs disappear from the index and their `store/<slug>/` directories are gone.

- [ ] **Step 5: Final commit (if any verification fixes were needed)**

```bash
git add -A
git commit -m "test: end-to-end verification of SPA wiring + filtered delete"
```

(If Steps 1–4 passed with no changes, skip this commit.)

---

## Self-Review Notes

- **Spec coverage:** SPA file placement (T7), static mount + index removal (T8), app.js live-data rewire (T9), `byte_size` on `/api/list` (T2), `POST /api/delete` with all seven filters + dry-run/confirm-token + empty-filter rejection + dual auth (T3/T4/T5/T6), `storage.delete_doc` (T1), `GET /api/whoami` (T6), `docs.zip` deletion (T7). All spec sections map to a task.
- **Out of scope (per spec), intentionally absent:** single-version deletion, an in-SPA delete control, server-side index filtering, soft-delete/undo.
- **Type consistency:** `find_docs` returns `{slug, title, latest_version}` (T3) and `delete_docs` consumes `slug` values from it (T4, via the `/api/delete` handler in T6). `make_delete_token`/`verify_delete_token` share `_canonical_filters` and the `DELETE_TOKEN_TTL` constant (T5). `/api/list` rows gain `byte_size` (T2), consumed by `applyFilters`/`renderIndex` in the rewired `app.js` (T9).
