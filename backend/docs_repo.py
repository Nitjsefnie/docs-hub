"""Document + version operations against the docs DB and the blob store."""
from __future__ import annotations

from backend import db, storage


def publish(slug: str, title: str, tags: list[str], project: str | None,
            posted_by: str, html: bytes) -> dict:
    """Create a new version of `slug` (creating the doc on first publish).
    Returns {slug, version, doc_id}."""
    if not storage.is_valid_slug(slug):
        raise ValueError(f"invalid slug: {slug!r}")
    with db.docs_conn() as c:
        row = c.execute("SELECT id, latest_version FROM docs WHERE slug=%s",
                        (slug,)).fetchone()
        if row is None:
            doc_id = c.execute(
                "INSERT INTO docs (slug, title, tags, project, latest_version) "
                "VALUES (%s,%s,%s,%s,0) RETURNING id",
                (slug, title, tags, project),
            ).fetchone()[0]
            version = 1
        else:
            doc_id, latest = row
            version = latest + 1
        path, size, digest = storage.store_blob(slug, version, html)
        c.execute(
            "INSERT INTO doc_versions "
            "(doc_id, version, posted_by, file_path, byte_size, sha256) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (doc_id, version, posted_by, path, size, digest),
        )
        c.execute(
            "UPDATE docs SET latest_version=%s, title=%s, tags=%s, project=%s, "
            "updated_at=now() WHERE id=%s",
            (version, title, tags, project, doc_id),
        )
        c.commit()
    return {"slug": slug, "version": version, "doc_id": doc_id}


def _version_row(slug: str, version: int) -> dict | None:
    with db.docs_conn() as c:
        row = c.execute(
            "SELECT v.version, v.posted_by, v.created_at, v.file_path, "
            "v.byte_size, v.sha256, d.title "
            "FROM doc_versions v JOIN docs d ON d.id=v.doc_id "
            "WHERE d.slug=%s AND v.version=%s",
            (slug, version),
        ).fetchone()
    if row is None:
        return None
    return {
        "version": row[0], "posted_by": row[1], "created_at": row[2],
        "file_path": row[3], "byte_size": row[4], "sha256": row[5],
        "title": row[6],
    }


def get_version(slug: str, version: int) -> dict | None:
    meta = _version_row(slug, version)
    if meta is None:
        return None
    meta["html"] = storage.read_blob(meta["file_path"])
    return meta


def get_latest(slug: str) -> dict | None:
    with db.docs_conn() as c:
        row = c.execute("SELECT latest_version FROM docs WHERE slug=%s",
                        (slug,)).fetchone()
    if row is None:
        return None
    return get_version(slug, row[0])


def is_public(slug: str) -> bool:
    """True iff the doc exists and is flagged public (anon-readable via /d/)."""
    with db.docs_conn() as c:
        row = c.execute("SELECT public FROM docs WHERE slug=%s",
                        (slug,)).fetchone()
    return bool(row and row[0])


def set_public(slug: str, public: bool) -> bool:
    """Set the slug's public flag. Returns False if the slug is unknown.
    The flag lives on the docs row, so re-publishing a version never
    touches it."""
    with db.docs_conn() as c:
        row = c.execute("UPDATE docs SET public=%s WHERE slug=%s RETURNING id",
                        (public, slug)).fetchone()
        c.commit()
    return row is not None


def list_docs(project: str | None = None, agent: str | None = None) -> list[dict]:
    """Newest-updated first. `agent` filters by the poster of the latest version."""
    sql = (
        "SELECT d.slug, d.title, d.tags, d.project, d.updated_at, "
        "d.latest_version, v.posted_by, v.byte_size, d.public "
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
         "byte_size": r[7], "public": r[8]}
        for r in rows
    ]


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


def list_versions(slug: str) -> list[dict]:
    """Version history for a slug, newest first."""
    with db.docs_conn() as c:
        rows = c.execute(
            "SELECT v.version, v.posted_by, v.created_at, v.byte_size, v.sha256 "
            "FROM doc_versions v JOIN docs d ON d.id=v.doc_id "
            "WHERE d.slug=%s ORDER BY v.version DESC",
            (slug,),
        ).fetchall()
    return [
        {"version": r[0], "posted_by": r[1], "created_at": r[2],
         "byte_size": r[3], "sha256": r[4]}
        for r in rows
    ]


def list_tags(project: str | None = None) -> list[dict]:
    """Every distinct tag in use with its usage count, most-used first.
    Lets agents pick from already-established tags rather than inventing
    new ones. `project` scopes to one project's docs."""
    sql = "SELECT unnest(d.tags) AS tag, COUNT(*) AS n FROM docs d"
    params: list = []
    if project is not None:
        sql += " WHERE d.project=%s"
        params.append(project)
    sql += " GROUP BY tag ORDER BY n DESC, tag ASC"
    with db.docs_conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [{"tag": r[0], "count": r[1]} for r in rows]
