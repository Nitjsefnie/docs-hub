import hashlib
import os
import pytest
from backend import storage


def test_valid_slugs():
    for s in ("analyst/2026-05-21-audit", "a", "a-b_c", "x/y/z"):
        assert storage.is_valid_slug(s), s


def test_invalid_slugs():
    for s in ("", "/lead", "trail/", "../etc", "Up", "a b", "a..b", "-lead"):
        assert not storage.is_valid_slug(s), s


def test_store_and_read_blob():
    html = b"<!doctype html><h1>hi</h1>"
    path, size, digest = storage.store_blob("analyst/doc", 1, html)
    assert size == len(html)
    assert digest == hashlib.sha256(html).hexdigest()
    assert os.path.isfile(path)
    assert storage.read_blob(path) == html


def test_store_blob_rejects_bad_slug():
    with pytest.raises(ValueError):
        storage.store_blob("../evil", 1, b"x")
