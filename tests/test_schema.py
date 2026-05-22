from backend import db


def test_tables_exist():
    with db.docs_conn() as c:
        for t in ("docs", "doc_versions"):
            row = c.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()
            assert row[0] is not None, f"{t} missing"
