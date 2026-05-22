"""Browser-facing routes: per-version artifact rendering for the SPA."""
from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import HTMLResponse, Response

from backend import docs_repo

router = APIRouter()


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
