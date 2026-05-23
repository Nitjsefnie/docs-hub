# docs-hub

A password-protected, versioned HTML-artifact hub. Agents publish HTML
documents (analyses, plans, reports, reviews) over an API; humans read
them in a browser. Re-publishing the same slug keeps prior versions
browsable.

This repo is the **server**. A separate CLI client can be built against
the documented API.

## What it does

- Agents `POST /api/publish` an HTML file under a slug, with title,
  tags, project, and an author handle. Each publish becomes a new
  version; old versions remain accessible.
- Humans log in with a user ID and password, then browse, search by
  project / agent / tag, and read documents in an iframe.
- Filter-based bulk delete is a two-step API: a preview call returns a
  confirm token; a follow-up call with the token executes the delete.

## Architecture

- Python + FastAPI + uvicorn; psycopg3 against Postgres.
- Metadata and the version index live in a Postgres database; HTML
  blobs are stored on local disk, one file per version.
- Human auth verifies user ID + password against a shared `users`
  table, then issues an HMAC-signed session cookie.
- Agent auth is a shared API key presented in an `X-API-Key` header.

## Layout

| Path | Role |
|------|------|
| `backend/` | FastAPI app — `db`, `schema`, `storage`, `auth`, `session`, `docs_repo`, `login`, `api`, `views`, `app` |
| `public/` | SPA (`index.html`, `app.js`, `styles.css`) served at `/` |
| `store/` | HTML blobs on disk, one file per version (git-ignored runtime data) |
| `tests/` | pytest suite |
| `deploy/` | systemd unit + nginx vhost template |
| `docs/` | design spec and implementation plan |

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -v
```

Tests build an isolated database from `backend/schema.sql` and a temp
blob store — see `tests/conftest.py`. No live network is touched.

## Deployment

- `deploy/` contains a systemd unit running `uvicorn backend.app:app`
  on a local port, plus an nginx vhost template to put in front of it.

Required environment for the running service:

- `DATABASE_URL_DOCS` — Postgres connection string for the docs database.
- `DATABASE_URL_AUTH` — Postgres connection string for the shared auth
  database (the `users` table used for human login).
- `DOCS_HUB_API_KEY` — shared key agents present in the `X-API-Key`
  header.
- `SESSION_SECRET` — HMAC secret used to sign session cookies.
- `STORE_ROOT` — path to the blob store directory.
- `COOKIE_SECURE` — `1` (default) to mark the session cookie `Secure`;
  set to `0` for local non-HTTPS development.

## Conventions

- TDD: write the failing test first, then the minimal implementation.
- Small, focused files — one clear responsibility each.
