# docs-hub

`docs.nitjsefni.eu` — a password-protected, versioned HTML-artifact hub.
Fleet agents publish HTML documents (analyses, plans, reports, reviews);
a human reads them in a browser. Re-publishing a slug keeps prior
versions browsable.

## Status

Design and implementation plan are complete; the server is not yet built.

- Spec: `docs/superpowers/specs/2026-05-21-docs-hub-design.md`
- Plan: `docs/superpowers/plans/2026-05-21-docs-hub.md` — 13 TDD tasks

Build the project by executing the plan task-by-task (superpowers
`subagent-driven-development` or `executing-plans`).

## Layout

| Path | Role |
|------|------|
| `backend/` | FastAPI app — db, schema, storage, auth, session, docs_repo, login, api, views, app |
| `store/` | HTML blobs on disk, one file per version (git-ignored runtime data) |
| `tests/` | pytest suite |
| `deploy/` | systemd unit + nginx vhost |
| `docs/superpowers/` | spec + plan |

The agent-facing **CLI is not in this repo** — per the fleet
canonical-scripts rule it lives at `~/.claude/scripts/docs_hub.py` and
ships via the setup bundle. This repo is the server only.

## Architecture

- Python + FastAPI + uvicorn; psycopg3 against Postgres.
- Metadata + the version index in the local `docs` database; HTML blobs
  on local disk under `store/`.
- Human auth: user ID + password verified against the shared `authdb`
  Postgres `users` table (same credentials as the other `*.nitjsefni.eu`
  services), then an HMAC session cookie.
- Agent auth: a shared API key (`DOCS_HUB_API_KEY`, from the environment).
- Served on local port 8084, behind nginx, Cloudflare-proxied.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -v
```

Tests build an isolated `docs_test` database from `backend/schema.sql`
and a temp blob store — see `tests/conftest.py`. No live network.

## Conventions

- TDD: write the failing test first, then the minimal implementation.
- Small, focused files — one clear responsibility each.
- Every commit carries a `Co-Authored-By` trailer for the model/agent
  that authored it.
