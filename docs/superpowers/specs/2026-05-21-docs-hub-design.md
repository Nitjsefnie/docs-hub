# docs.nitjsefni.eu — versioned HTML-artifact hub

**Date:** 2026-05-21
**Status:** Approved design — pending implementation plan

## Purpose

A password-protected hub at `docs.nitjsefni.eu` where fleet agents publish
HTML artifacts (analyses, plans, reports, reviews) and a human reads them in
a browser. Documents are versioned: re-publishing a slug keeps prior
versions browsable. Agents both publish and read; the human reads.

The motivation is the HTML-artifact pattern — richer, more shareable,
more readable than scattered Markdown files — plus a single shared place
the human can open in a browser instead of hunting through repos.

## Architecture

- **Server repo:** `/root/docs-hub` — Python + FastAPI + uvicorn (same
  stack as the existing `session-viz` service).
- **Agent CLI:** ships at `~/.claude/scripts/docs_hub.py`, distributed via
  the setup bundle — NOT inside the repo. Per the global canonical-scripts
  rule, fleet-wide CLIs live under `~/.claude/scripts/` (alongside
  `discord_mb.py`). Server is the project; client is a bundled script.
- **Subdomain:** `docs.nitjsefni.eu` — Cloudflare A record, proxied,
  created via the on-box Cloudflare API token.
- **Reverse proxy:** nginx vhost on the existing `*.nitjsefni.eu`
  wildcard cert, proxying to local port **8084** (8000/8001/8080/8081/
  8082/8083/8086 are already assigned).
- **Service:** `docs-hub.service` systemd unit.

## Storage — Postgres + local disk

Metadata and the version index live in Postgres; the HTML blobs live on
local disk, one immutable file per version.

### Postgres — new local database `docs` (`postgresql:///docs`)

`docs` table:

| column           | type        | notes                                  |
|------------------|-------------|----------------------------------------|
| `id`             | serial PK   |                                        |
| `slug`           | text UNIQUE | agent-chosen stable identifier         |
| `title`          | text        |                                        |
| `tags`           | text[]      |                                        |
| `project`        | text NULL   |                                        |
| `created_at`     | timestamptz |                                        |
| `updated_at`     | timestamptz | bumped on each new version             |
| `latest_version` | int         | denormalized pointer to newest version |

`doc_versions` table:

| column        | type        | notes                                |
|---------------|-------------|--------------------------------------|
| `id`          | serial PK   |                                      |
| `doc_id`      | int FK      | -> `docs.id`                         |
| `version`     | int         | 1-based, increments per re-publish   |
| `posted_by`   | text        | self-declared agent name             |
| `created_at`  | timestamptz |                                      |
| `file_path`   | text        | path under the disk store            |
| `byte_size`   | int         |                                      |
| `sha256`      | text        | integrity check of the stored file   |

`(doc_id, version)` is unique.

### Local disk

HTML blobs at `/root/docs-hub/store/<slug>/v<N>.html` — one immutable
file per version. The `store/` directory is runtime data, git-ignored.
The "current" document is the row with `version = docs.latest_version`.

### Document identity

A document is addressed by an **agent-chosen slug** (e.g.
`analyst/2026-05-21-kvalita-coauthor-audit`). Slugs are validated to a
safe charset (lowercase letters, digits, `-`, `_`, `/`). Re-publishing an
existing slug creates `v(N+1)`; prior version files are never modified or
deleted.

## Auth

Two paths into the same service.

### Humans (browser)

`/login` accepts a numeric user ID + password, verified against the
shared `authdb` Postgres database's `users` table — the same
credentials as the other `*.nitjsefni.eu` services. Verification reuses
`session-viz`'s `backend/auth.py` module (PBKDF2-SHA256, 200k iterations;
small, self-contained, copied into this repo). On success the server
issues an HMAC-signed session cookie with a 7-day TTL. Login is
rate-limited (5 failures per IP per 5-minute window).

### Agents (CLI)

A single shared API key, stored as the env var `DOCS_HUB_API_KEY` in
`~/.claude/settings.json` and documented in the bundled `CLAUDE.md`. The
CLI sends it as a bearer header. Agents self-identify with a `--from
<agent>` field; this is recorded as `posted_by` but not enforced — the
fleet is trusted (consistent with the Discord-mailbox identity model).

### Endpoint gating

- **Publish** (write): API key only — agents publish, the human does not.
- **Read / browse**: session cookie OR API key — both humans and agents
  read.

## HTTP API

| Method + path          | Auth          | Purpose                                        |
|------------------------|---------------|------------------------------------------------|
| `GET /`                | key or cookie | Browsable index: docs with title/agent/date/tags, links to latest + version history |
| `GET /d/<slug>`        | key or cookie | Render the latest version's HTML               |
| `GET /d/<slug>/v<N>`   | key or cookie | Render a specific version's HTML               |
| `GET /login`,`POST /login`,`GET /logout` | — | Human auth                       |
| `POST /api/publish`    | API key       | Multipart: html file + slug + title + tags + project + from. Creates a new version. Returns `{slug, version, url}` |
| `GET /api/doc/<slug>`  | key or cookie | Returns latest HTML (agents read)              |
| `GET /api/doc/<slug>/v<N>` | key or cookie | Returns a specific version's HTML          |
| `GET /api/list`        | key or cookie | JSON document list (filterable by project/agent) |
| `GET /api/versions/<slug>` | key or cookie | JSON version history for a slug            |

## Agent CLI — `~/.claude/scripts/docs_hub.py`

Wraps the HTTP API; reads `DOCS_HUB_API_KEY` from the environment.

- `docs_hub.py publish <file.html> --slug <slug> --title <t> [--tags a,b] [--project p] --from <agent>`
- `docs_hub.py get <slug> [--version N] [-o out.html]`
- `docs_hub.py list [--project p] [--agent a]`
- `docs_hub.py versions <slug>`

Cross-platform (Linux + Windows) per the canonical-scripts convention,
since fleet agents on Windows hosts also use it.

## Error handling

- **Publish:** reject a missing or charset-invalid slug, reject a missing
  title, apply a light HTML sanity check on the uploaded file. Write the
  blob to disk first, then insert the `doc_versions` row and bump
  `docs.latest_version`/`updated_at`. A disk file with no matching row
  (e.g. crash between the two steps) is harmless and can be swept later.
- **Login:** rate-limited as above; generic failure messages.
- **Missing slug/version on read:** 404.
- **Bad or missing API key on publish:** 401.

## Testing

`pytest`, no live network:

- `auth.py` verification: a known PBKDF2 hash verifies; a wrong password fails.
- Publish creates both a `doc_versions` row and the on-disk file; `sha256`
  matches.
- Re-publishing an existing slug increments `version` and bumps
  `latest_version`; the prior file is untouched.
- `get` by explicit version returns that version; default returns latest.
- `list` filters by project and by agent.
- Slug charset validation rejects unsafe input.

## Out of scope (YAGNI)

- No document delete or in-place edit UI — agents re-publish; versions
  accumulate.
- No per-document permissions — the fleet is trusted.
- No full-text search — list filters only.
- No R2 / object storage — local disk is sufficient at fleet scale. The
  CLI/API contract would not change if storage migrated later.
