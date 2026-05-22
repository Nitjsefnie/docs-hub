"""Browser-facing routes: the document index and per-version rendering."""
from __future__ import annotations

import html as _html

from fastapi import APIRouter
from starlette.responses import HTMLResponse, Response

from backend import docs_repo

router = APIRouter()

_INDEX_HEAD = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>docs.nitjsefni.eu</title><style>
 body{background:#0b0d10;color:#dde;font-family:sans-serif;margin:0;padding:24px}
 h1{font-size:18px;color:#9bd}
 table{border-collapse:collapse;width:100%}
 td,th{text-align:left;padding:6px 10px;border-bottom:1px solid #25303c;font-size:13px}
 a{color:#6cf;text-decoration:none}
 .tag{background:#1a2230;color:#9bd;padding:1px 6px;border-radius:3px;font-size:11px}
</style></head><body><h1>docs.nitjsefni.eu</h1><table>
<tr><th>Title</th><th>Slug</th><th>Project</th><th>By</th><th>Updated</th><th>Ver</th></tr>
"""


@router.get("/")
async def index() -> HTMLResponse:
    rows = []
    for d in docs_repo.list_docs():
        slug = _html.escape(d["slug"])
        rows.append(
            f"<tr><td><a href='/d/{slug}'>{_html.escape(d['title'])}</a></td>"
            f"<td>{slug}</td><td>{_html.escape(d['project'] or '')}</td>"
            f"<td>{_html.escape(d['posted_by'])}</td>"
            f"<td>{d['updated_at'].strftime('%Y-%m-%d %H:%M')}</td>"
            f"<td><a href='/d/{slug}/versions'>v{d['latest_version']}</a></td></tr>"
        )
    return HTMLResponse(_INDEX_HEAD + "".join(rows) + "</table></body></html>")


@router.get("/d/{slug:path}/v{version}")
async def render_version(slug: str, version: int) -> Response:
    doc = docs_repo.get_version(slug, version)
    if doc is None:
        return Response("Not found", status_code=404, media_type="text/plain")
    return HTMLResponse(doc["html"])


@router.get("/d/{slug:path}")
async def render_latest(slug: str) -> Response:
    doc = docs_repo.get_latest(slug)
    if doc is None:
        return Response("Not found", status_code=404, media_type="text/plain")
    return HTMLResponse(doc["html"])
