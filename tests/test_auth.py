from backend import auth


def test_set_then_verify_roundtrip():
    config = {}
    auth.set_web_password(config, "hunter2")
    assert auth.has_web_password(config)
    assert auth.verify_web_password(config, "hunter2")
    assert not auth.verify_web_password(config, "wrong")


def test_verify_missing_hash_is_false():
    assert not auth.verify_web_password({}, "anything")
