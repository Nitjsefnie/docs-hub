# tests/test_docs_repo.py
import pytest
from backend import docs_repo


def test_publish_creates_v1():
    res = docs_repo.publish("analyst/x", "Title X", ["t1"], "proj", "analyst",
                            b"<h1>v1</h1>")
    assert res["version"] == 1
    assert res["slug"] == "analyst/x"
    latest = docs_repo.get_latest("analyst/x")
    assert latest["version"] == 1
    assert latest["html"] == b"<h1>v1</h1>"


def test_republish_increments_version():
    docs_repo.publish("analyst/x", "Title X", [], None, "analyst", b"<h1>v1</h1>")
    res2 = docs_repo.publish("analyst/x", "Title X v2", [], None, "kimi",
                             b"<h1>v2</h1>")
    assert res2["version"] == 2
    assert docs_repo.get_latest("analyst/x")["html"] == b"<h1>v2</h1>"
    # prior version still retrievable
    v1 = docs_repo.get_version("analyst/x", 1)
    assert v1["html"] == b"<h1>v1</h1>"


def test_get_missing_returns_none():
    assert docs_repo.get_latest("nope/nope") is None
    assert docs_repo.get_version("nope/nope", 9) is None


def test_list_and_filter():
    docs_repo.publish("a/one", "One", [], "alpha", "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/two", "Two", [], "beta", "kimi", b"<h1>2</h1>")
    assert {d["slug"] for d in docs_repo.list_docs()} == {"a/one", "a/two"}
    assert [d["slug"] for d in docs_repo.list_docs(project="alpha")] == ["a/one"]


def test_list_versions():
    docs_repo.publish("a/v", "V", [], None, "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/v", "V", [], None, "analyst", b"<h1>2</h1>")
    vs = docs_repo.list_versions("a/v")
    assert [v["version"] for v in vs] == [2, 1]


def test_publish_bad_slug_raises():
    with pytest.raises(ValueError):
        docs_repo.publish("../evil", "X", [], None, "analyst", b"x")
