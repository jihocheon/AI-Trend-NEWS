import json
import tempfile
import unittest
import urllib.error
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from radar import collectors
from radar.cli import main
from radar.http import HTTP, IntegrationError
from radar.intelligence import GeminiReasoner, SampleReasoner
from radar.models import Analysis
from radar.notion import Notion
from radar.pipeline import run
from radar.store import Store

NOW = "2026-01-05T00:00:00+00:00"


class FakeHTTP:
    def __init__(self, responses=(), xml=b""):
        self.responses = iter(responses)
        self.xml = xml
        self.calls = []

    def request(self, *args, **kwargs):
        return self.xml

    def json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def gemini_reply(**overrides):
    raw = dict(topic="AI agents", category="Agents", summary="Tools and planning", decision="Create",
               target_id=None, reason="Relevant")
    raw.update(overrides)
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(raw)}]}}]}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_offline_evaluation_and_rerun(self):
        counts = run(self.store, collectors.sample(), SampleReasoner(), now=NOW)
        self.assertEqual(counts, {"Create": 2, "Update": 1, "Skip": 1})
        topics = self.store.topics()
        self.assertEqual(len(topics), 2)
        actual = self.store.db.execute("""SELECT s.external_id,h.action,t.name FROM history h
          JOIN sources s ON s.id=h.source_id LEFT JOIN topics t ON t.id=h.topic_id ORDER BY h.id""").fetchall()
        self.assertEqual([tuple(r) for r in actual], [
            ("sample-rss-1", "Create", "Retrieval augmented generation"),
            ("sample-arxiv-1", "Update", "Retrieval augmented generation"),
            ("sample-github-1", "Create", "AI agents"),
            ("sample-noise", "Skip", None)])
        self.assertEqual(topics[0]["name"], "Retrieval augmented generation")
        self.assertGreater(topics[0]["score"], topics[1]["score"])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM relationships").fetchone()[0], 3)
        self.assertEqual(run(self.store, collectors.sample(), SampleReasoner(), now=NOW),
                         {"Create": 0, "Update": 0, "Skip": 0})
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM history").fetchone()[0], 4)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM runs WHERE status='success'").fetchone()[0], 2)

    def test_source_revisions_and_retrieval(self):
        source = collectors.sample()[0]
        run(self.store, [source], SampleReasoner(), now=NOW)
        revision = replace(source, text=source.text + " New evaluation results.")
        counts = run(self.store, [revision], SampleReasoner(), now=NOW)
        self.assertEqual(counts["Update"], 1)
        self.assertEqual(len(self.store.topics()), 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM sources").fetchone()[0], 2)
        history = self.store.db.execute("SELECT before_json,after_json FROM history WHERE action='Update'").fetchone()
        self.assertNotEqual(history[0], history[1])

    def test_archive_keeps_data_and_new_evidence_reactivates(self):
        run(self.store, collectors.sample(), SampleReasoner(), now=NOW)
        run(self.store, [], SampleReasoner(), now="2026-05-05T00:00:00+00:00")
        self.assertTrue(all(t["archived"] for t in self.store.topics()))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM sources").fetchone()[0], 4)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM history WHERE action='Archive'").fetchone()[0], 2)
        new = replace(collectors.sample()[0], external_id="new-evidence")
        run(self.store, [new], SampleReasoner(), now="2026-05-06T00:00:00+00:00")
        self.assertEqual(self.store.topics()[0]["archived"], 0)

    def test_failed_decision_is_retryable(self):
        class Broken:
            def analyze(self, source, candidates):
                return Analysis("X", "AI", "Summary", "Update", 999)
        with self.assertRaises(ValueError):
            run(self.store, collectors.sample(), Broken(), now=NOW)
        self.assertEqual(self.store.db.execute("SELECT sum(processed) FROM sources").fetchone()[0], 0)
        self.assertEqual(self.store.db.execute("SELECT status FROM runs").fetchone()[0], "failed")
        self.assertEqual(run(self.store, [], SampleReasoner(), now=NOW)["Create"], 2)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "radar.db")
            first = Store(path)
            run(first, collectors.sample(), SampleReasoner(), now=NOW)
            first.close()
            second = Store(path)
            self.assertEqual(len(second.topics()), 2)
            second.close()


class AdapterTests(unittest.TestCase):
    def test_rss(self):
        http = FakeHTTP(xml=b'<rss><channel><item><guid>1</guid><title>AI</title><link>https://example.com</link><description>Research</description></item></channel></rss>')
        source = collectors.rss(http, "https://example.com/feed")[0]
        self.assertEqual((source.external_id, source.text), ("1", "Research"))

    def test_atom_and_arxiv(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>paper:1</id><title> AI research </title><summary>Neural models</summary><link href="https://arxiv.org/abs/1"/><published>2026-01-01</published></entry></feed>'
        self.assertEqual(collectors.rss(FakeHTTP(xml=xml), "https://example.com")[0].url, "https://arxiv.org/abs/1")
        self.assertEqual(collectors.arxiv(FakeHTTP(xml=xml))[0].kind, "arxiv")

    def test_github(self):
        http = FakeHTTP([{"items": [{"id": 1, "full_name": "org/agents", "html_url": "https://github.com/org/agents",
                                    "description": "AI agents", "updated_at": "2026-01-01"}]}])
        self.assertEqual(collectors.github(http)[0].external_id, "1")
        self.assertNotIn("Authorization", http.calls[0][2]["headers"])

    def test_gemini_decision(self):
        http = FakeHTTP([gemini_reply()])
        decision = GeminiReasoner(http, "test-only").analyze(collectors.sample()[0], [])
        self.assertEqual(decision.decision, "Create")
        self.assertIn("x-goog-api-key", http.calls[0][2]["headers"])
        self.assertNotIn("test-only", http.calls[0][1])

    def test_gemini_rejects_invalid_target_and_empty_summary(self):
        for reply in [gemini_reply(decision="Update", target_id=999), gemini_reply(summary=""),
                      gemini_reply(decision="Delete"), {"candidates": []}]:
            with self.subTest(reply=reply), self.assertRaises(IntegrationError):
                GeminiReasoner(FakeHTTP([reply]), "test-only").analyze(collectors.sample()[0], [])

    def test_notion_create_update_archive_and_noop(self):
        store = Store(":memory:")
        run(store, [collectors.sample()[0]], SampleReasoner(), now=NOW)
        http = FakeHTTP([{"id": "page-1"}, {}, {"results": [{"id": "block-1"}]}, {}, {}, {}])
        notion = Notion(http, "test-only", "a" * 32)
        self.assertEqual(notion.sync(store), 1)
        self.assertEqual(notion.sync(store), 0)
        self.assertEqual(store.topics()[0]["notion_block_id"], "block-1")
        run(store, [collectors.sample()[1]], SampleReasoner(), now=NOW)
        self.assertEqual(notion.sync(store), 1)
        self.assertTrue(http.calls[-1][1].endswith("blocks/block-1"))
        store.rank_and_archive("2027-01-01T00:00:00+00:00")
        notion.sync(store)
        self.assertEqual(http.calls[-1][2]["data"], {"archived": True})
        self.assertEqual(sum(c[0] == "POST" for c in http.calls), 1)
        store.close()

    def test_notion_failure_retains_remote_identity_and_pending(self):
        store = Store(":memory:")
        run(store, [collectors.sample()[0]], SampleReasoner(), now=NOW)
        notion = Notion(FakeHTTP([{"id": "page-1"}, IntegrationError("Unavailable")]), "test-only", "a" * 32)
        with self.assertRaises(IntegrationError):
            notion.sync(store)
        topic = store.topics()[0]
        self.assertEqual(topic["notion_page_id"], "page-1")
        self.assertEqual(topic["sync_pending"], 1)
        store.close()

    def test_local_scheduler_repeats_without_reprocessing(self):
        with tempfile.TemporaryDirectory() as folder, patch("builtins.print") as output:
            with patch("radar.cli.time.sleep", side_effect=[None, KeyboardInterrupt]):
                status = main(["--db", folder + "/test.db", "--log", folder + "/run.log",
                               "run", "--interval", "60"])
            self.assertEqual(status, 130)
            self.assertEqual(output.call_count, 2)
            self.assertIn('"Create": 0', output.call_args[0][0])

    def test_transport_rejects_plaintext_and_sanitizes_proxy_failure(self):
        with self.assertRaises(IntegrationError):
            HTTP().request("GET", "http://example.com")
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = urllib.error.URLError(
                OSError("Tunnel connection failed: 403 Forbidden secret-test"))
            with self.assertRaises(IntegrationError) as caught:
                HTTP().request("GET", "https://example.com")
            self.assertIn("allowlist", str(caught.exception))
            self.assertNotIn("secret-test", str(caught.exception))

    def test_http_write_is_not_retried(self):
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(
                "https://example.com", 429, "rate limited", {}, None)
            with self.assertRaises(IntegrationError):
                HTTP().request("POST", "https://example.com", data={})
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_missing_credentials_and_cli_sample(self):
        with self.assertRaises(ValueError):
            GeminiReasoner(FakeHTTP(), None)
        with tempfile.TemporaryDirectory() as folder, patch("builtins.print") as output:
            args = ["--db", folder + "/test.db", "--log", folder + "/run.log"]
            self.assertEqual(main(args + ["run"]), 0)
            self.assertIn('"Create": 2', output.call_args[0][0])
            self.assertIn("decision=Update", Path(folder + "/run.log").read_text())
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(main(args + ["run", "--mode", "live"]), 1)


if __name__ == "__main__":
    unittest.main()
