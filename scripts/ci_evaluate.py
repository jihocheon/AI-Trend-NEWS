"""Run the existing evaluation against an isolated fixture-backed SQLite corpus."""
import json
import os
import tempfile
from pathlib import Path

from radar.bootstrap import bootstrap
from radar.evaluate import evaluate
from radar.store import Store


class FixtureSources:
    def __init__(self):
        path = Path(__file__).resolve().parents[1] / "tests/fixtures/ci_sources.json"
        self.responses = json.loads(path.read_text())["responses"]
        self.calls = []

    def request(self, method, url):
        if method != "GET" or url not in self.responses:
            raise AssertionError("CI fixture source is missing; external fallback is forbidden")
        self.calls.append(url)
        return self.responses[url].encode()


def main():
    if os.getenv("RADAR_CI_NETWORK_BLOCKED") != "1":
        raise SystemExit("Run CI evaluation with scripts/ci_offline on PYTHONPATH")
    with tempfile.TemporaryDirectory(prefix="radar-ci-evaluation-") as folder:
        store = Store(str(Path(folder) / "evaluation.sqlite3"))
        try:
            sources = FixtureSources()
            first = bootstrap(store, sources)
            second = bootstrap(store, sources)
            assert first["generation_requests"] == 0
            assert first["updated_references"] == 3
            assert second["updated_references"] == 0
            assert len(set(sources.calls)) == 5
            result = evaluate(store)
            # Reuse all existing labels; thresholds are explicit, enforced, and fixture-only.
            assert len(result["topic_queries"]) == 6
            assert len(result["document_queries"]) == 3
            assert result["topic_hit_at_1"] == 1.0, result
            assert result["topic_mrr_at_3"] == 1.0, result
            assert result["document_precision_at_1"] == 1.0, result
            assert result["unrelated_topic_results"] == 0, result
            print(json.dumps({"corpus": "deterministic CI fixtures; no live originals", **result},
                             ensure_ascii=False, indent=2))
        finally:
            store.close()


if __name__ == "__main__":
    main()
