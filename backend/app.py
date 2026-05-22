"""FastAPI entrypoint for docs-hub."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from backend import api, db, login, session, views

_REPO_ROOT = Path(__file__).resolve().parent.parent
db.load_dotenv(str(_REPO_ROOT / ".env"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.schema_check()
    yield


app = FastAPI(title="docs-hub", docs_url=None, redoc_url=None, lifespan=lifespan)
app.middleware("http")(session.auth_middleware)
app.include_router(login.router)
app.include_router(api.router)
app.include_router(views.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}
