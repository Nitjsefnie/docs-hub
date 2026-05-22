import os
from backend import db


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
