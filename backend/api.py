"""/api/* routes. Publishing requires the agent API key; reads accept the
key or a human cookie (the middleware already enforced one of the two)."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request, UploadFile
from starlette.responses import HTMLResponse, JSONResponse, Response

from backend import docs_repo, session

router = APIRouter(prefix="/api")


def _require_agent(request: Request) -> JSONResponse | None:
    if not session.has_valid_api_key(request):
        return JSONResponse({"ok": False, "error": "API key required"},
                            status_code=401)
    return None


@router.post("/publish")
async def publish(request: Request, file: UploadFile,
                  slug: str = Form(...), title: str = Form(...),
                  tags: str = Form(""), project: str = Form(""),
                  from_: str = Form(..., alias="from")) -> Response:
    denied = _require_agent(request)
    if denied is not None:
        return denied
    html = await file.read()
    if not html:
        return JSONResponse({"ok": False, "error": "empty file"}, status_code=400)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        res = docs_repo.publish(slug, title, tag_list, project or None,
                                from_, html)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({
        "ok": True, "slug": res["slug"], "version": res["version"],
        "url": f"/d/{res['slug']}",
    })


@router.get("/doc/{slug:path}")
async def get_doc(slug: str) -> Response:
    doc = docs_repo.get_latest(slug)
    if doc is None:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return HTMLResponse(doc["html"])


@router.get("/list")
async def api_list(project: str = "", agent: str = "") -> JSONResponse:
    docs = docs_repo.list_docs(project or None, agent or None)
    for d in docs:
        d["updated_at"] = d["updated_at"].isoformat()
    return JSONResponse({"ok": True, "docs": docs})


@router.get("/versions/{slug:path}")
async def api_versions(slug: str) -> JSONResponse:
    vs = docs_repo.list_versions(slug)
    if not vs:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    for v in vs:
        v["created_at"] = v["created_at"].isoformat()
    return JSONResponse({"ok": True, "slug": slug, "versions": vs})
