import os
import psycopg
from backend import db, docs_repo


def test_load_dotenv_sets_missing_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO_DOCS_TEST=bar\n# comment\n\n", encoding="utf-8")
    os.environ.pop("FOO_DOCS_TEST", None)
    db.load_dotenv(str(env))
    assert os.environ["FOO_DOCS_TEST"] == "bar"


def test_load_dotenv_does_not_overwrite(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO_DOCS_TEST2=fromfile\n", encoding="utf-8")
    os.environ["FOO_DOCS_TEST2"] = "preset"
    db.load_dotenv(str(env))
    assert os.environ["FOO_DOCS_TEST2"] == "preset"


def _kill_pooled_backends() -> int:
    """Terminate every docs-pool backend server-side, the way a Postgres
    restart does. The pool keeps handing out the now-dead connections."""
    db.docs_pool()  # ensure the pool exists and has opened at least one conn
    with db.docs_conn() as c:
        c.execute("SELECT 1").fetchone()
        c.commit()
    with psycopg.connect(os.environ["DATABASE_URL_DOCS"], autocommit=True) as k:
        return k.execute(
            "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid()"
        ).fetchone()[0]


def test_docs_conn_survives_server_side_disconnect():
    """A Postgres restart must not poison the pool: the next checkout gets a
    live connection instead of raising OperationalError."""
    _kill_pooled_backends()
    with db.docs_conn() as c:
        assert c.execute("SELECT 1").fetchone()[0] == 1
        c.commit()


def test_publish_survives_server_side_disconnect():
    """The failure that actually bit: publish raised HTTP 500 for hours after
    a Postgres restart because the first pooled query died."""
    _kill_pooled_backends()
    res = docs_repo.publish("t/reconnect", "Reconnect", [], None,
                            "tester", b"<p>hi</p>")
    assert res["version"] == 1
