import time
from backend import session


def test_mint_then_verify():
    tok = session.make_session_token(42)
    assert session.verify_session_token(tok) == 42


def test_tampered_token_rejected():
    tok = session.make_session_token(42)
    bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    assert session.verify_session_token(bad) is None


def test_expired_token_rejected(monkeypatch):
    old = int(time.time()) - session.SESSION_COOKIE_MAX_AGE - 10
    monkeypatch.setattr(time, "time", lambda: old)
    tok = session.make_session_token(42)
    monkeypatch.undo()
    assert session.verify_session_token(tok) is None


def test_garbage_token_rejected():
    assert session.verify_session_token("not.a.token") is None


def test_delete_token_roundtrip():
    f = {"project": "analyst"}
    tok = session.make_delete_token(f)
    assert session.verify_delete_token(tok, f) is True


def test_delete_token_filter_order_insensitive():
    tok = session.make_delete_token({"project": "p", "author": "a"})
    assert session.verify_delete_token(tok, {"author": "a", "project": "p"}) is True


def test_delete_token_rejects_changed_filters():
    tok = session.make_delete_token({"project": "alpha"})
    assert session.verify_delete_token(tok, {"project": "beta"}) is False


def test_delete_token_rejects_tampered():
    tok = session.make_delete_token({"project": "p"})
    bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    assert session.verify_delete_token(bad, {"project": "p"}) is False


def test_delete_token_rejects_garbage():
    assert session.verify_delete_token("not-a-token", {"project": "p"}) is False


def test_delete_token_rejects_expired(monkeypatch):
    old = int(time.time()) - session.DELETE_TOKEN_TTL - 10
    monkeypatch.setattr(time, "time", lambda: old)
    tok = session.make_delete_token({"project": "p"})
    monkeypatch.undo()
    assert session.verify_delete_token(tok, {"project": "p"}) is False
