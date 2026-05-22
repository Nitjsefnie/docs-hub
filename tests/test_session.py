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
