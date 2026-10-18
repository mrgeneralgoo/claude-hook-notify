import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import notify_recap  # noqa: E402
import notify as ln  # noqa: E402


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        return self.body[:limit]


class TestRecap(unittest.TestCase):
    def setUp(self):
        self.config = {"enabled": True, "base_url": "https://api.example/v1",
                       "model": "test-model", "api_key_env": "RECAP_TEST_KEY"}
        self.env = patch.dict("os.environ", {"RECAP_TEST_KEY": "secret"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_posts_openai_compatible_body_and_returns_text(self):
        body = json.dumps({"choices": [{"finish_reason": "stop",
                                         "message": {"content": "Done."}}]}).encode()
        with patch.object(notify_recap.urllib.request.OpenerDirector, "open",
                          return_value=_Response(body)) as opened:
            # build_opener yields an OpenerDirector whose open is patched above.
            result = notify_recap.generate(self.config, "task", "x" * 601, 5)
        self.assertEqual(result, "Done.")
        request = opened.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["max_tokens"], 512)
        self.assertEqual(payload["stream"], False)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.full_url, "https://api.example/v1/chat/completions")

    def test_invalid_config_and_missing_key_fall_back(self):
        self.assertIsNone(notify_recap.generate({}, "task", "x" * 601, 5))
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(notify_recap.generate(self.config, "task", "x" * 601, 5))

    def test_literal_key_only_and_precedence(self):
        response = json.dumps({"choices": [{"finish_reason": "stop",
                                              "message": {"content": "Done."}}]}).encode()
        cases = [
            ({"api_key": "literal-fake-key"}, "Bearer literal-fake-key"),
            ({"api_key_env": "RECAP_TEST_KEY"}, "Bearer secret"),
            ({"api_key": "literal-fake-key", "api_key_env": "MISSING"},
             "Bearer literal-fake-key"),
            ({"api_key": "literal-fake-key", "api_key_env": []},
             "Bearer literal-fake-key"),
        ]
        with patch.dict("os.environ", {"RECAP_TEST_KEY": "secret"}, clear=True):
            for extras, expected in cases:
                with self.subTest(extras=extras), patch.object(
                        notify_recap.urllib.request.OpenerDirector, "open",
                        return_value=_Response(response)) as opened:
                    config = dict(self.config, **extras)
                    self.assertEqual(notify_recap.generate(
                        config, "task", "x" * 601, 5), "Done.")
                    self.assertEqual(opened.call_args.args[0].get_header("Authorization"),
                                     expected)

    def test_invalid_literal_key_does_not_fall_back_to_environment(self):
        response = json.dumps({"choices": [{"finish_reason": "stop",
                                              "message": {"content": "Done."}}]}).encode()
        with patch.dict("os.environ", {"RECAP_TEST_KEY": "env-fake-key"}):
            for literal in ("", 123, "fake\rkey", "fake\nkey"):
                with self.subTest(literal=literal), patch.object(
                        notify_recap.urllib.request.OpenerDirector, "open",
                        return_value=_Response(response)) as opened:
                    config = dict(self.config, api_key=literal)
                    self.assertIsNone(notify_recap.generate(config, "task", "x" * 601, 5))
                    opened.assert_not_called()

    def test_malformed_or_partial_response_falls_back(self):
        for payload in (b"{}", b"not json", json.dumps({"choices": [{
                "finish_reason": "length", "message": {"content": "partial"}}]}).encode()):
            with self.subTest(payload=payload), patch.object(
                    notify_recap.urllib.request.OpenerDirector, "open",
                    return_value=_Response(payload)):
                self.assertIsNone(notify_recap.generate(self.config, "", "x" * 601, 5))

    def test_long_text_is_not_requested(self):
        self.assertIsNone(notify_recap.generate(self.config, "", "x" * 600, 5))

    def test_invalid_endpoint_is_rejected(self):
        for url in ("http://api.example/v1", "https://user:pass@api.example/v1",
                    "https://api.example/v1?token=x", "https://api.example/v1#frag"):
            config = dict(self.config, base_url=url)
            self.assertIsNone(notify_recap.generate(config, "", "x" * 601, 5))

    def test_builder_uses_recap_without_mutating_raw_stats(self):
        stats = {"assistant_text": "original" * 100, "assistant_recap": "short recap",
                 "summary_reliable": True, "user_prompt": "task", "tool_calls": 0}
        payload = {"hook_event_name": "Stop", "cwd": "."}
        with patch.object(ln, "git_info", return_value={}), patch.object(
                ln, "project_name", return_value="project"):
            message = ln.build_hook_message(payload, {"include_summary": True}, stats)
        self.assertIn("short recap", message.body)
        self.assertNotIn("original", message.body)
        self.assertTrue(stats["assistant_text"].startswith("original"))


if __name__ == "__main__":
    unittest.main()
