"""Codex native hooks use the existing delivery pipeline."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import notify as ln


class TestCodex(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user = self.root / "config.json"
        self.config = {"channel": "bark", "device_key": "testdevice"}
        self.write_config()
        for target, value in (("CONFIG_PATH", self.user),
                              ("LEGACY_CONFIG_PATH", self.root / "missing.json")):
            p = patch.object(ln, target, value)
            p.start()
            self.addCleanup(p.stop)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        for target, value in (("post", (True, "ok")), ("git_info", {}),
                              ("log", None), ("generate_recap", (None, "disabled"))):
            p = patch.object(ln, target, return_value=value)
            setattr(self, target, p.start())
            self.addCleanup(p.stop)
        for target in ("parse_transcript", "find_transcript"):
            p = patch.object(ln, target, side_effect=AssertionError("Codex must not read Claude history"))
            p.start()
            self.addCleanup(p.stop)
        self.native = {"hook_event_name": "Stop", "session_id": "thread-123",
                       "cwd": str(self.root), "last_assistant_message": "Native reply"}

    def write_config(self):
        self.user.write_text(json.dumps(self.config))

    def test_bark_default_icons_follow_harness(self):
        icons = {}
        for source in ("claude", "codex"):
            cfg = ln.load_config(str(self.root), source=source)
            preview = ln.render(cfg, ln.Message(title="preview"))
            _, sent = ln.CHANNELS["bark"].request(ln.destination(cfg), preview)
            icons[source] = sent["icon"]
            self.assertEqual(preview["icon"], sent["icon"])
            self.assertEqual(sent["icon"], ln.get_harness(source).notification_icon)
        self.assertNotEqual(icons["claude"], icons["codex"])

    def test_bark_custom_icons_and_legacy_override(self):
        for icon, expected in (
            ({"claude": "https://example.com/custom.png"},
             ln.get_harness("codex").notification_icon),
            ({"codex": "https://example.com/codex.png"}, "https://example.com/codex.png"),
            ("https://example.com/shared.png", "https://example.com/shared.png"),
            ({"codex": ""}, ""),
        ):
            with self.subTest(icon=icon):
                self.config.pop("icon", None)
                self.config.pop("icons", None)
                self.config["icons" if isinstance(icon, dict) else "icon"] = icon
                self.write_config()
                cfg = ln.load_config(str(self.root), source="codex")
                self.assertEqual(cfg["icon"], expected)
                _, sent = ln.CHANNELS["bark"].request(ln.destination(cfg), {})
                self.assertEqual(sent.get("icon", ""), expected)

    def test_bark_named_icons_cannot_be_overridden_by_project(self):
        self.config = {"destination": "phone", "destinations": {"phone": {
            "channel": "bark", "device_key": "testdevice",
            "icons": {"codex": "https://example.com/trusted.png"},
        }}}
        self.write_config()
        project = self.root / ".codex"
        project.mkdir()
        (project / "notify.json").write_text(json.dumps({
            "icons": {"codex": "https://example.com/untrusted.png"}}))
        cfg = ln.load_config(str(self.root), source="codex")
        self.assertEqual(cfg["icon"], "https://example.com/trusted.png")
        self.assertTrue(any("icon" in w for w in cfg["_warnings"]))

    def test_per_harness_icon_overrides_legacy_without_changing_other_harness(self):
        self.config.update(icon="https://example.com/legacy-claude.png",
                           icons={"codex": "https://example.com/codex.png"})
        self.write_config()
        self.assertEqual(ln.load_config(str(self.root), source="claude")["icon"],
                         "https://example.com/legacy-claude.png")
        self.assertEqual(ln.load_config(str(self.root), source="codex")["icon"],
                         "https://example.com/codex.png")

    def test_invalid_icon_mapping_stops_delivery(self):
        for icons in ({"codex": 42}, [], None, "https://example.com/icon.png"):
            with self.subTest(icons=icons):
                self.config["icons"] = icons
                self.write_config()
                self.run_hook()
                self.post.assert_not_called()

    def test_hook_and_manual_send_use_codex_icon(self):
        self.run_hook()
        self.assertEqual(self.post.call_args[0][0]["icon"],
                         ln.get_harness("codex").notification_icon)
        with contextlib.redirect_stdout(io.StringIO()):
            result = ln.main(["send", "--source", "codex", "-t", "test", "-m", "hello"])
        self.assertEqual(result, 0)
        self.assertEqual(self.post.call_args[0][0]["icon"],
                         ln.get_harness("codex").notification_icon)

    def run_hook(self, payload=None, dry_run=False):
        raw = json.dumps(self.native if payload is None else payload)
        args = ["hook", "--source", "codex"]
        if dry_run:
            args.append("--dry-run")
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(raw)), contextlib.redirect_stdout(output):
            result = ln.main(args)
        self.assertEqual(result, 0)
        return output.getvalue()

    def sent_text(self):
        return json.dumps(self.post.call_args.args[1], ensure_ascii=False)

    def test_native_stop_uses_shared_delivery_and_codex_source(self):
        self.assertEqual(self.run_hook(), "")
        self.assertEqual(self.post.call_count, 1)
        self.assertIn("Native reply", self.sent_text())
        self.assertIn("Codex · Stop", self.sent_text())
        self.assertIn("thread-1", self.sent_text())
        self.assertNotIn("Claude", self.sent_text())
        self.assertEqual(self.post.call_args.args[1]["group"], "Codex")
        self.assertNotIn("次工具调用", self.sent_text())
        self.assertNotIn("用时", self.sent_text())

    def test_native_stop_does_not_invent_task_text_from_extra_fields(self):
        self.run_hook(dict(self.native, _user_prompt="Private task", prompt="Private task",
                           **{"input-messages": ["Private task"]}))
        self.assertIn("Native reply", self.sent_text())
        self.assertNotIn("Private task", self.sent_text())
        self.assertNotIn("本轮任务", self.sent_text())

    def test_dry_run_never_sends_or_recaps(self):
        self.native["last_assistant_message"] = "x" * 1000
        output = self.run_hook(dry_run=True)
        self.assertIn("Codex", json.dumps(json.loads(output)))
        self.post.assert_not_called()
        self.generate_recap.assert_not_called()

    def test_unknown_and_malformed_events_do_not_send(self):
        cases = [{}, {"hook_event_name": "Notification"}, {"type": "agent-turn-complete"},
                 dict(self.native, hook_event_name=None), dict(self.native, cwd=[]),
                 dict(self.native, cwd=""), dict(self.native, session_id=42),
                 dict(self.native, session_id=""), dict(self.native, last_assistant_message=[]),
                 dict(self.native, stop_hook_active="false")]
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.run_hook(payload), "")
        self.post.assert_not_called()

    def test_invalid_json_and_oversized_input_are_ignored(self):
        for raw in ("", "{broken", "[]", "null", "x" * (ln.MAX_STDIN_BYTES + 1)):
            with self.subTest(raw=raw[:20]), patch("sys.stdin", io.StringIO(raw)):
                self.assertEqual(ln.main(["hook", "--source", "codex"]), 0)
        self.post.assert_not_called()

    def test_continuation_stop_is_ignored(self):
        for event in ("Stop", "SubagentStop"):
            self.run_hook(dict(self.native, hook_event_name=event, stop_hook_active=True))
        self.post.assert_not_called()

    def test_native_subagent_uses_own_payload_reply(self):
        self.config["events"] = ["SubagentStop"]
        self.write_config()
        self.run_hook(dict(self.native, hook_event_name="SubagentStop",
                           last_assistant_message="Subagent reply",
                           transcript_path="parent-history", agent_transcript_path="child-history"))
        self.assertIn("Subagent reply", self.sent_text())
        self.assertIn("子任务完成", self.sent_text())

    def test_permission_request_maps_to_notification_without_tool_input(self):
        payload = dict(self.native, hook_event_name="PermissionRequest", tool_name="Bash",
                       permission_description="Build needs approval",
                       tool_input={"command": "SECRET-COMMAND", "token": "SECRET-TOKEN"})
        self.config["debug"] = True
        self.write_config()
        self.run_hook(payload)
        text = self.sent_text()
        self.assertIn("请求授权", text)
        self.assertIn("Build needs approval", text)
        self.assertIn("Codex · PermissionRequest", text)
        self.assertNotIn("SECRET", text)
        logs = str(self.log.call_args_list)
        for value in ("SECRET", "Native reply", "Build needs approval"):
            self.assertNotIn(value, logs)

    def test_permission_respects_existing_event_filter(self):
        self.config["events"] = ["Stop"]
        self.write_config()
        self.run_hook(dict(self.native, hook_event_name="PermissionRequest", tool_name="Bash"))
        self.post.assert_not_called()

    def test_privacy_disables_reply_and_permission_description(self):
        self.config["include_summary"] = False
        self.write_config()
        self.run_hook()
        self.assertNotIn("Native reply", self.sent_text())
        self.run_hook(dict(self.native, hook_event_name="PermissionRequest",
                           permission_description="Private reason"))
        self.assertNotIn("Private reason", self.sent_text())
        self.generate_recap.assert_not_called()

    def test_unknown_timing_respects_min_duration_filter(self):
        self.config["min_duration_seconds"] = 1
        self.write_config()
        self.run_hook()
        self.post.assert_not_called()

    def test_event_allowlist_and_quiet_hours_apply(self):
        for config in ({"events": []}, {"events": ["Stop"], "quiet_hours": "invalid"}):
            self.config.update(config)
            self.write_config()
            self.run_hook()
        self.post.assert_not_called()

    def test_removed_events_are_ignored_before_loading_config(self):
        with patch.object(ln, "load_config", side_effect=AssertionError("unsupported event")):
            for event in ("UserPromptSubmit", "SessionEnd"):
                self.assertEqual(self.run_hook(dict(self.native, hook_event_name=event)), "")
        self.post.assert_not_called()
        self.generate_recap.assert_not_called()

    def test_long_reply_uses_existing_recap_pipeline(self):
        self.config["recap"] = {"enabled": True}
        self.write_config()
        self.generate_recap.return_value = ("Short summary", "")
        self.run_hook(dict(self.native, last_assistant_message="x" * 800))
        self.generate_recap.assert_called_once()
        self.assertEqual(self.generate_recap.call_args.args[1], "")
        self.assertIn("AI 摘要", self.sent_text())
        self.assertIn("Short summary", self.sent_text())

    def test_codex_project_settings_are_separate_and_restrictive(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "notify.json").write_text('{"events": []}')
        self.run_hook()
        self.assertEqual(self.post.call_count, 1)
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "notify.json").write_text(json.dumps({
            "include_summary": False, "channel": "slack", "webhook_url": "https://evil.invalid",
            "recap": {"enabled": True}, "debug": True}))
        cfg = ln.load_config(str(self.root), source="codex")
        self.assertEqual(cfg["channel"], "bark")
        self.assertNotIn("webhook_url", cfg)
        self.assertNotIn("recap", cfg)
        self.assertNotIn("debug", cfg)
        self.assertFalse(cfg["include_summary"])
        self.run_hook()
        self.assertNotIn("Native reply", self.sent_text())
        self.assertEqual(ln.effective_events(ln.load_config(str(self.root))), [])

    def test_bad_project_config_fails_closed_without_claude_fallback(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "notify.json").write_text('{broken')
        self.run_hook()
        self.post.assert_not_called()

    def test_codex_project_can_select_user_registered_destination(self):
        self.config["destinations"] = {"phone": {"channel": "bark", "device_key": "otherdevice"}}
        self.write_config()
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "notify.json").write_text('{"destination": "phone"}')
        cfg = ln.load_config(str(self.root), source="codex")
        self.assertEqual(cfg["device_key"], "otherdevice")

    def test_manual_codex_send_uses_thread_id_without_history_lookup(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": "thread-manual"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ln.main(["send", "--source", "codex", "-m", "Manual message"]), 0)
        self.assertIn("Codex", self.sent_text())
        self.assertIn("thread-m", self.sent_text())
        self.assertNotIn("Claude", self.sent_text())

    def test_manual_source_inference_and_explicit_override(self):
        args = ln.build_parser().parse_args(["send"])
        with patch.dict(os.environ, {"CODEX_THREAD_ID": "thread"}):
            self.assertEqual(ln.command_source(args), "codex")
            args.source = "claude"
            self.assertEqual(ln.command_source(args), "claude")
            args.source = None
            with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "session"}):
                self.assertEqual(ln.command_source(args), "claude")
            self.assertEqual(ln.build_parser().parse_args(["hook"]).source, "claude")

    def test_cli_native_stdin_dry_run_subprocess(self):
        self.config.update(include_summary=True, quiet_hours=None, min_duration_seconds=0,
                           events=["Stop"], debug=False, recap={"enabled": False})
        self.write_config()
        env = {"PATH": os.defpath, "CLAUDE_HOOK_NOTIFY_CONFIG": str(self.user)}
        result = subprocess.run([sys.executable, str(Path(ln.__file__)), "hook", "--source", "codex",
                                 "--dry-run"], input=json.dumps(self.native), env=env, text=True,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Native reply", json.loads(result.stdout)["markdown"])


class TestCodexPackaging(unittest.TestCase):
    def test_packaged_commands_run_from_a_plugin_path_with_spaces(self):
        repo = Path(__file__).resolve().parent.parent
        # A portable root manifest shadows the compatibility manifest in Codex
        # 0.167.0 and causes these hooks to disappear from plugin/read.
        self.assertFalse((repo / "plugin.json").exists())
        manifest = json.loads((repo / ".codex-plugin" / "plugin.json").read_text())
        claude = json.loads((repo / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["version"], claude["version"])
        hook_path = manifest["hooks"]
        hooks = json.loads((repo / hook_path).read_text())["hooks"]
        self.assertEqual(set(hooks), {"Stop", "SubagentStop", "PermissionRequest"})
        self.assertNotIn("UserPromptSubmit", claude["hooks"])
        self.assertIn("SessionEnd", claude["hooks"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin = root / "plugin with spaces"
            plugin.symlink_to(repo, target_is_directory=True)
            config = root / "config.json"
            config.write_text(json.dumps({
                "channel": "bark", "device_key": "testdevice",
                "events": ["Stop", "Notification", "SubagentStop"],
                "include_summary": True, "quiet_hours": None, "min_duration_seconds": 0,
                "debug": False, "recap": {"enabled": False},
            }))
            env = {"PATH": os.defpath, "PLUGIN_ROOT": str(plugin),
                   "CLAUDE_HOOK_NOTIFY_CONFIG": str(config)}
            for event, groups in hooks.items():
                with self.subTest(event=event):
                    handler = groups[0]["hooks"][0]
                    self.assertGreater(handler["timeout"], ln.HOOK_BUDGET_SECONDS)
                    payload = {"session_id": "packaged-thread", "cwd": temp,
                               "hook_event_name": event, "last_assistant_message": "Packaged reply",
                               "tool_name": "Bash", "permission_description": "Review this action"}
                    result = subprocess.run(
                        ["/bin/sh", "-c", handler["command"] + " --dry-run"],
                        input=json.dumps(payload), cwd=temp, env=env, text=True,
                        capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    body = json.loads(result.stdout)
                    self.assertEqual(body["group"], "Codex")
                    self.assertIn("Codex · " + event, body["markdown"])
                    self.assertNotIn("badge", body)


if __name__ == "__main__":
    unittest.main()
