"""Harness factory contracts and a third adapter through the real notification pipeline."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import notify as ln
from notify_harnesses import DEFAULT_HARNESS, HARNESSES, Harness, get_harness


class ExampleHarness(Harness):
    name = "example"
    label = "Example Agent"
    project_dir = ".example"
    legacy_project_config = "legacy-notify.json"
    session_env = "EXAMPLE_SESSION_ID"

    def normalize_hook(self, payload):
        if payload.get("event") != "finished":
            return None
        return dict(payload, hook_event_name="Stop")

    def parse_stats(self, payload, transcript_reader):
        return {"assistant_text": payload.get("answer", ""),
                "user_prompt": payload.get("task", ""), "session_name": "Example task",
                "summary_reliable": True}


class TestHarnessFactory(unittest.TestCase):
    def test_registered_and_unknown_harnesses(self):
        self.assertEqual(set(HARNESSES), {"claude", "codex"})
        self.assertEqual(DEFAULT_HARNESS, "claude")
        for name in HARNESSES:
            self.assertIs(get_harness(name), HARNESSES[name])
            self.assertEqual(get_harness(name).name, name)
        for name in (None, "", "unknown", [], {}):
            with self.subTest(name=name):
                self.assertIsNone(get_harness(name))

    def test_unknown_source_cannot_fall_back_to_a_destination(self):
        args = ln.build_parser().parse_args(["hook"])
        args.source = "unknown"
        with patch("sys.stdin", io.StringIO('{"hook_event_name":"Stop"}')), \
                patch.object(ln, "load_config") as config, patch.object(ln, "post") as post:
            self.assertEqual(ln.cmd_hook(args), 0)
        config.assert_not_called()
        post.assert_not_called()
        self.assertIn("_fatal", ln.load_config(source="unknown"))
        with self.assertRaises(ValueError):
            ln.command_source(args)
        with self.assertRaises(ValueError):
            ln.build_hook_message({"_source": "unknown"}, {})
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            ln.build_parser().parse_args(["hook", "--source", "unknown"])
        self.assertEqual(error.exception.code, 2)


class TestThirdHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user = self.root / "user.json"
        self.user.write_text(json.dumps({"channel": "bark", "device_key": "testdevice"}))
        self.project = self.root / ".example"
        self.project.mkdir()
        for p in (patch.dict(HARNESSES, {"example": ExampleHarness()}),
                  patch.dict(os.environ, {}, clear=True),
                  patch.object(ln, "CONFIG_PATH", self.user),
                  patch.object(ln, "LEGACY_CONFIG_PATH", self.root / "missing.json"),
                  patch.object(ln, "git_info", return_value={}),
                  patch.object(ln, "log"),
                  patch.object(ln, "find_transcript", return_value=""),
                  patch.object(os, "getcwd", return_value=str(self.root))):
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(ln, "post", return_value=(True, "ok"))
        self.post = p.start()
        self.addCleanup(p.stop)
        self.payload = {"event": "finished", "session_id": "example-thread", "cwd": str(self.root),
                        "answer": "Example answer", "task": "Example prompt", "_source": "codex"}

    def run_hook(self):
        with patch("sys.stdin", io.StringIO(json.dumps(self.payload))), \
                patch.object(ln, "parse_transcript", side_effect=AssertionError("wrong history policy")):
            self.assertEqual(ln.main(["hook", "--source", "example"]), 0)
        return self.post.call_args.args[1]

    def test_third_harness_flows_through_cli_stats_labels_and_session(self):
        body = self.run_hook()
        self.assertEqual(body["group"], "Example Agent")
        self.assertIn("Example task", body["title"])
        self.assertIn("Example answer", body["markdown"])
        self.assertIn("Example prompt", body["markdown"])
        self.assertIn("Example Agent · Stop", body["markdown"])
        self.assertIn("example-", body["markdown"])
        self.assertNotIn("Codex", json.dumps(body))

    def test_project_metadata_preserves_shared_config_trust_and_privacy(self):
        (self.project / "legacy-notify.json").write_text(json.dumps({
            "include_summary": False, "channel": "slack", "webhook_url": "https://evil.invalid"}))
        cfg = ln.load_config(str(self.root), source="example")
        self.assertEqual(cfg["channel"], "bark")
        self.assertNotIn("webhook_url", cfg)
        self.assertFalse(cfg["include_summary"])
        body = self.run_hook()
        self.assertNotIn("Example answer", body["markdown"])
        self.assertNotIn("Example prompt", body["markdown"])
        (self.project / "notify.json").write_text('{"events": []}')
        self.post.reset_mock()
        with patch("sys.stdin", io.StringIO(json.dumps(self.payload))):
            self.assertEqual(ln.main(["hook", "--source", "example"]), 0)
        self.post.assert_not_called()

    def test_manual_send_and_doctor_use_adapter_metadata(self):
        with patch.dict(os.environ, {"EXAMPLE_SESSION_ID": "example-manual"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ln.command_source(ln.build_parser().parse_args(["send"])), "example")
            self.assertEqual(ln.main(["send", "-m", "Manual text"]), 0)
            self.assertEqual(ln.main(["doctor", "--source", "example"]), 0)
        body = self.post.call_args.args[1]
        self.assertEqual(body["group"], "Example Agent")
        self.assertIn("example-", body["markdown"])
        self.assertIn("example", output.getvalue())
        with patch.dict(os.environ, {"EXAMPLE_SESSION_ID": "e", "CODEX_THREAD_ID": "c",
                                     "CLAUDE_CODE_SESSION_ID": "a"}):
            self.assertEqual(ln.command_source(ln.build_parser().parse_args(["send"])), "claude")

    def test_default_claude_hook_overwrites_payload_source(self):
        payload = {"_source": "codex", "hook_event_name": "Stop", "cwd": str(self.root)}
        stats = {"assistant_text": "Claude reply", "session_name": "Claude task"}
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                patch.object(ln, "parse_transcript", return_value=stats) as reader:
            self.assertEqual(ln.main(["hook"]), 0)
        reader.assert_called_once()
        body = self.post.call_args.args[1]
        self.assertEqual(body["group"], "Claude Code")
        self.assertIn("Claude reply", body["markdown"])


if __name__ == "__main__":
    unittest.main()
