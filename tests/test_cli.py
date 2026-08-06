import os, subprocess, sys, threading, time
from pathlib import Path
import uvicorn

CLI = Path.home() / ".agent-bundle" / "scripts" / "docs_hub.py"

_SERVER = None


def _spawn_server():
    """Start the test server once per session. The thread is a daemon and is
    never joined, so re-binding port 8099 for a second test always failed."""
    global _SERVER
    if _SERVER is not None:
        return _SERVER
    from backend.app import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=8099, log_level="error")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):
        time.sleep(0.1)
        if server.started:
            _SERVER = server
            return server
    raise RuntimeError("server did not start")


def test_cli_publish_get_list(tmp_path):
    _spawn_server()
    env = {**os.environ, "DOCS_HUB_URL": "http://127.0.0.1:8099",
           "DOCS_HUB_API_KEY": "test-api-key"}
    doc = tmp_path / "d.html"
    doc.write_text("<h1>cli</h1>", encoding="utf-8")
    pub = subprocess.run(
        [sys.executable, str(CLI), "publish", str(doc), "--slug", "cli/demo",
         "--title", "CLI Demo", "--from", "analyst"],
        capture_output=True, text=True, env=env)
    assert pub.returncode == 0, pub.stderr
    assert "cli/demo" in pub.stdout
    out = tmp_path / "got.html"
    get = subprocess.run(
        [sys.executable, str(CLI), "get", "cli/demo", "-o", str(out)],
        capture_output=True, text=True, env=env)
    assert get.returncode == 0, get.stderr
    assert out.read_text(encoding="utf-8") == "<h1>cli</h1>"
    lst = subprocess.run([sys.executable, str(CLI), "list"],
                         capture_output=True, text=True, env=env)
    assert "cli/demo" in lst.stdout


def test_cli_tags(tmp_path):
    _spawn_server()
    env = {**os.environ, "DOCS_HUB_URL": "http://127.0.0.1:8099",
           "DOCS_HUB_API_KEY": "test-api-key"}
    doc = tmp_path / "d.html"
    doc.write_text("<h1>t</h1>", encoding="utf-8")
    for slug, tags in (("cli/a", "spec,draft"), ("cli/b", "spec")):
        subprocess.run(
            [sys.executable, str(CLI), "publish", str(doc), "--slug", slug,
             "--title", slug, "--tags", tags, "--from", "analyst"],
            capture_output=True, text=True, env=env, check=True)
    out = subprocess.run([sys.executable, str(CLI), "tags"],
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    # "<count>  <tag>" lines, most-used first
    lines = [ln.strip() for ln in out.stdout.strip().splitlines()]
    assert lines[0].endswith("spec") and lines[0].startswith("2")
    assert any(ln.endswith("draft") and ln.startswith("1") for ln in lines)
