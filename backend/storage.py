"""HTML blob storage on local disk + slug validation.

Layout: <STORE_ROOT>/<slug>/v<N>.html — one immutable file per version.
"""
from __future__ import annotations

import hashlib
import os
import re

# slug: lowercase alnum segments joined by '/'; segment chars [a-z0-9_-];
# each segment starts and ends alphanumeric; no '..', no leading/trailing '/'.
_SEGMENT = r"[a-z0-9]([a-z0-9_-]*[a-z0-9])?"
_SLUG_RE = re.compile(rf"^{_SEGMENT}(/{_SEGMENT})*$")


def is_valid_slug(slug: str) -> bool:
    return bool(slug) and len(slug) <= 200 and _SLUG_RE.fullmatch(slug) is not None


def _store_root() -> str:
    return os.environ["STORE_ROOT"]


def blob_path(slug: str, version: int) -> str:
    """Absolute path for a version's HTML file. Raises ValueError on bad slug."""
    if not is_valid_slug(slug):
        raise ValueError(f"invalid slug: {slug!r}")
    return os.path.join(_store_root(), slug, f"v{version}.html")


def store_blob(slug: str, version: int, html: bytes) -> tuple[str, int, str]:
    """Write the HTML file. Returns (path, byte_size, sha256_hex)."""
    path = blob_path(slug, version)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(html)
    return path, len(html), hashlib.sha256(html).hexdigest()


def read_blob(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
