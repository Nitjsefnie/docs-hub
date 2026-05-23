# tests/test_docs_repo.py
import os
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


def test_list_docs_includes_byte_size():
    body = b"<h1>sized body</h1>"
    docs_repo.publish("a/sz", "Sized", [], None, "analyst", body)
    d = docs_repo.list_docs()[0]
    assert d["byte_size"] == len(body)


def test_find_docs_by_each_filter():
    docs_repo.publish("a/one", "Alpha One", ["x"], "alpha", "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/two", "Beta Two", ["y"], "beta", "kimi", b"<h1>2</h1>")
    assert [d["slug"] for d in docs_repo.find_docs({"slug": "a/one"})] == ["a/one"]
    assert [d["slug"] for d in docs_repo.find_docs({"project": "alpha"})] == ["a/one"]
    assert [d["slug"] for d in docs_repo.find_docs({"author": "kimi"})] == ["a/two"]
    assert [d["slug"] for d in docs_repo.find_docs({"tag": "x"})] == ["a/one"]
    assert [d["slug"] for d in docs_repo.find_docs({"q": "beta"})] == ["a/two"]
    assert {d["slug"] for d in docs_repo.find_docs({})} == {"a/one", "a/two"}


def test_find_docs_and_combines():
    docs_repo.publish("a/one", "Alpha One", [], "alpha", "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/two", "Alpha Two", [], "alpha", "kimi", b"<h1>2</h1>")
    res = docs_repo.find_docs({"project": "alpha", "author": "kimi"})
    assert [d["slug"] for d in res] == ["a/two"]


def test_find_docs_shape():
    docs_repo.publish("a/one", "Alpha One", [], "alpha", "analyst", b"<h1>1</h1>")
    d = docs_repo.find_docs({"project": "alpha"})[0]
    assert set(d) == {"slug", "title", "latest_version"}


def test_delete_docs_removes_rows_versions_blobs():
    docs_repo.publish("a/del", "Del", [], None, "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/del", "Del", [], None, "analyst", b"<h1>2</h1>")
    n = docs_repo.delete_docs(["a/del"])
    assert n == 1
    assert docs_repo.get_latest("a/del") is None
    assert docs_repo.list_versions("a/del") == []
    blob_dir = os.path.join(os.environ["STORE_ROOT"], "a", "del")
    assert not os.path.exists(blob_dir)


def test_delete_docs_unknown_slug_counts_zero():
    assert docs_repo.delete_docs(["nope/nope"]) == 0


def test_delete_docs_partial_set():
    docs_repo.publish("a/keep", "Keep", [], None, "analyst", b"<h1>k</h1>")
    docs_repo.publish("a/drop", "Drop", [], None, "analyst", b"<h1>d</h1>")
    assert docs_repo.delete_docs(["a/drop", "missing/x"]) == 1
    assert docs_repo.get_latest("a/keep") is not None
    assert docs_repo.get_latest("a/drop") is None


def test_list_tags_empty():
    assert docs_repo.list_tags() == []


def test_list_tags_distinct_with_counts_most_used_first():
    docs_repo.publish("a/one", "One", ["spec", "draft"], "alpha", "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/two", "Two", ["spec"], "beta", "kimi", b"<h1>2</h1>")
    tags = docs_repo.list_tags()
    by = {t["tag"]: t["count"] for t in tags}
    assert by == {"spec": 2, "draft": 1}
    assert tags[0]["tag"] == "spec" and tags[0]["count"] == 2


def test_list_tags_scoped_to_project():
    docs_repo.publish("a/one", "One", ["spec"], "alpha", "analyst", b"<h1>1</h1>")
    docs_repo.publish("a/two", "Two", ["draft"], "beta", "kimi", b"<h1>2</h1>")
    assert docs_repo.list_tags(project="alpha") == [{"tag": "spec", "count": 1}]
