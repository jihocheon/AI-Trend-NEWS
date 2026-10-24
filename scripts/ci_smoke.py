"""Exercise the installed console script outside the checkout with temporary state."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    if os.getenv("RADAR_CI_NETWORK_BLOCKED") != "1":
        raise SystemExit("Run CLI smoke with scripts/ci_offline on PYTHONPATH")
    cli = Path(sys.executable).with_name("ai-radar")
    assert cli.is_file(), "Project console script was not installed"
    with tempfile.TemporaryDirectory(prefix="radar-ci-smoke-") as folder:
        db = Path(folder) / "smoke.sqlite3"
        log = Path(folder) / "smoke.log"

        def command(*args):
            result = subprocess.run([str(cli), "--db", str(db), "--log", str(log), *args],
                                    cwd=folder, check=True, capture_output=True, text=True, timeout=30)
            return json.loads(result.stdout)

        first = command("run", "--mode", "sample")
        assert first == {"mode": "sample", "Create": 2, "Update": 1, "Skip": 1}, first
        topics = command("topics")
        assert len(topics) == 2
        second = command("run", "--mode", "sample")
        assert second == {"mode": "sample", "Create": 0, "Update": 0, "Skip": 0}, second
        assert db.is_file() and "decision=Update" in log.read_text()
        from fastapi.testclient import TestClient
        from radar.chat import ChatService
        from radar.chat_web import create_app
        with TestClient(create_app(ChatService(str(db))),base_url="http://localhost") as client:
            assert client.get("/").status_code==200
            assert client.get("/static/chat.js").status_code==200
            assert client.get("/static/chat.css").status_code==200
            assert client.get("/api/health").json()["knowledge_ready"]
        print("Installed CLI smoke passed: offline sample, persisted topics, unchanged rerun")


if __name__ == "__main__":
    main()
