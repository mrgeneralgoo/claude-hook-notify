# -*- coding: utf-8 -*-
"""0.5.0：结果分节的来源标签与顺序、Bark 分节留白、未读角标、recap 失败日志。"""

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import notify as ln  # noqa: E402
from notify_channels import bark  # noqa: E402
from notify_channels.base import Message  # noqa: E402

BARK_CFG = {"channel": "bark", "device_key": "abc123", "events": ["Stop", "UserPromptSubmit"]}


def stats_for(**kw):
    stats = {"user_prompt": "修复登录", "assistant_text": "已完成。", "summary_reliable": True,
             "tool_calls": 0, "turn_kind": "prompt"}
    stats.update(kw)
    return stats


def build(payload=None, cfg=None, **kw):
    payload = dict({"hook_event_name": "Stop", "cwd": os.getcwd()}, **(payload or {}))
    with patch.object(ln, "git_info", return_value={}), patch.object(
            ln, "project_name", return_value="proj"):
        return ln.build_hook_message(payload, cfg or {}, stats_for(**kw))


class TestResultLabelsAndOrder(unittest.TestCase):
    def test_original_label(self):
        body = build().body
        self.assertIn("**回复原文**\n已完成。", body)
        self.assertNotIn("节选", body)

    def test_truncated_original_label(self):
        body = build(assistant_text="长" * 700).body
        self.assertIn("**回复原文 · 节选**", body)

    def test_recap_label(self):
        body = build(assistant_text="长" * 700, assistant_recap="结论\n- 要点").body
        self.assertIn("**AI 摘要**\n结论\n- 要点", body)
        self.assertNotIn("回复原文", body)

    def test_result_first_without_generic_headline(self):
        for event in ("Stop", "SubagentStop"):
            body = build({"hook_event_name": event}).body
            self.assertTrue(body.startswith("**回复原文**"), body)
            self.assertLess(body.index("回复原文"), body.index("本轮任务"))
            self.assertNotIn("已完成本轮任务", body)
            self.assertNotIn("子任务执行完成", body)

    def test_pending_background_keeps_headline_first(self):
        task = {"id": "1", "type": "shell", "status": "running", "description": "sleep"}
        body = build({"background_tasks": [task]}).body
        self.assertTrue(body.startswith("**本轮已结束，1 个后台任务仍在运行"), body)
        self.assertLess(body.index("回复原文"), body.index("本轮任务"))
        self.assertLess(body.index("本轮任务"), body.index("sleep"))

    def test_no_result_keeps_headline(self):
        body = build(assistant_text="").body
        self.assertTrue(body.startswith("**Claude Code 已完成本轮任务**"), body)

    def test_task_is_one_plain_line(self):
        prompt = ("> [@x](mention://user/1) 请看这段\n> 第二行引用\n\n- 列表项\n"
                  + "很长的需求描述 " * 40)
        msg = build(user_prompt=prompt, assistant_text="答复正文")
        task = msg.body.split("**本轮任务**\n", 1)[1].split("\n")[0]
        self.assertNotIn("\n", task)
        self.assertFalse(task.startswith(">"))
        self.assertLessEqual(len(task), 120)
        self.assertTrue(task.startswith("[@x](mention://user/1) 请看这段 第二行引用 列表项"), task)
        self.assertNotIn("> ", task)
        # 结果分节仍然独占一个 block
        self.assertTrue(msg.blocks[0].startswith("**回复原文**"))
        self.assertTrue(any(b.startswith("**本轮任务**\n") and "\n" not in b.split("\n", 1)[1]
                            for b in msg.blocks))

    def test_blocks_join_to_body(self):
        msg = build()
        self.assertEqual("\n".join(msg.blocks), msg.body)


class TestBarkRender(unittest.TestCase):
    def test_blocks_separated_by_blank_lines_and_badge(self):
        msg = Message(title="t", body="a\nb", blocks=["**A**\nx", "**B**\ny"], badge=3)
        out = bark.CHANNEL.render(msg)
        self.assertIn("**A**\n\nx\n\n**B**\n\ny", out["markdown"].replace("  \n", "\n"))
        self.assertEqual(out["badge"], 3)

    def test_label_spacing_only_for_whole_line_bold(self):
        self.assertEqual(bark.space_block("**A**\nx\n- y"), "**A**\n\nx\n- y")
        self.assertEqual(bark.space_block("**A** 正文\nx"), "**A** 正文\nx")
        self.assertEqual(bark.space_block("**A**"), "**A**")

    def test_needs_you_is_time_sensitive(self):
        self.assertEqual(bark.CHANNEL.render(Message(title="t", status="decision"))["level"],
                         "timeSensitive")
        for status in ("success", "running", "info"):
            self.assertNotIn("level", bark.CHANNEL.render(Message(title="t", status=status)))

    def test_needs_you_states_share_one_title(self):
        heads = {}
        for ntype in ("permission_prompt", "elicitation_dialog", "idle_prompt"):
            msg = build({"hook_event_name": "Notification", "notification_type": ntype,
                         "message": "Claude is waiting for your input"})
            self.assertTrue(msg.title.startswith("🔴 等你处理"), msg.title)
            self.assertEqual(msg.status, "decision")
            heads[ntype] = msg.blocks[0]
        self.assertEqual(heads["permission_prompt"], "**请求授权**")
        self.assertEqual(heads["elicitation_dialog"], "**在等你回答**")
        self.assertEqual(heads["idle_prompt"], "**在等你的下一步指示**")
        idle = build({"hook_event_name": "Notification", "notification_type": "idle_prompt",
                      "message": "Claude is waiting for your input"})
        self.assertNotIn("waiting for your input", idle.body, "等待输入的英文原文与标题重复")

    def test_subtask_is_green_success(self):
        msg = build({"hook_event_name": "SubagentStop"})
        self.assertTrue(msg.title.startswith("🟢 子任务完成"), msg.title)
        self.assertEqual(msg.status, "success")

    def test_badge_only_when_positive_int(self):
        for value in (None, 0, -1, True, "3"):
            self.assertNotIn("badge", bark.CHANNEL.render(Message(title="t", badge=value)))

    def test_without_blocks_uses_body(self):
        self.assertIn("plain", bark.CHANNEL.render(Message(title="t", body="plain"))["markdown"])

    def test_destination_badge_false_drops_badge(self):
        body = bark.CHANNEL.render(Message(title="t", badge=2))
        _, kept = bark.CHANNEL.request({"device_key": "abc"}, body)
        _, dropped = bark.CHANNEL.request({"device_key": "abc", "badge": False}, body)
        self.assertEqual(kept["badge"], 2)
        self.assertNotIn("badge", dropped)

    def test_bool_badge_passes_validation(self):
        cfg = dict(BARK_CFG, badge=False)
        warnings = []
        ln.validate_credentials(cfg, warnings)
        self.assertEqual(warnings, [])
        self.assertNotIn("_fatal", cfg)
        ok, why, _, body = ln.prepare_request(cfg, {"badge": 1}, ("api.day.app",))
        self.assertTrue(ok, why)
        self.assertNotIn("badge", body)
        warnings = []
        ln.validate_credentials(dict(BARK_CFG, badge="no"), warnings)
        self.assertEqual(len(warnings), 1)


class TestBadgeState(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for p in (patch.object(ln, "CONFIG_DIR", self.dir),
                  patch.object(ln, "LOG_PATH", self.dir / "debug.log")):
            p.start()
            self.addCleanup(p.stop)
        self.path = self.dir / "badge.json"

    def run_hook(self, payload, cfg=None, sent=(True, "ok"), extra_args=()):
        args = ln.build_parser().parse_args(["hook", *extra_args])
        out = io.StringIO()
        cfg = dict(BARK_CFG if cfg is None else cfg)
        with patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(out), \
                patch.object(ln, "load_config", return_value=cfg), \
                patch.object(ln, "parse_for_event", return_value=stats_for()), \
                patch.object(ln, "git_info", return_value={}), \
                patch.object(ln, "post", return_value=sent) as post:
            rc = ln.cmd_hook(args)
        return rc, out.getvalue(), post

    def stop(self, sid="s1"):
        return {"hook_event_name": "Stop", "session_id": sid, "cwd": os.getcwd()}

    def n(self, sid="s1"):
        return json.loads(self.path.read_text())["sessions"][sid]["n"]

    def test_increments_on_success_and_total_is_sent(self):
        _, _, post = self.run_hook(self.stop())
        self.assertEqual(post.call_args.args[1]["badge"], 1)
        _, _, post = self.run_hook(self.stop("s2"))
        self.assertEqual(post.call_args.args[1]["badge"], 2)
        _, _, post = self.run_hook(self.stop())
        self.assertEqual(post.call_args.args[1]["badge"], 3)
        self.assertEqual((self.n("s1"), self.n("s2")), (2, 1))
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_failed_send_does_not_increment(self):
        self.run_hook(self.stop(), sent=(False, "HTTP 500"))
        self.assertFalse(self.path.exists())

    def test_dry_run_does_not_increment(self):
        self.run_hook(self.stop(), extra_args=("--dry-run",))
        self.assertFalse(self.path.exists())

    def test_opt_out_does_not_count(self):
        _, _, post = self.run_hook(self.stop(), cfg=dict(BARK_CFG, badge=False))
        self.assertNotIn("badge", post.call_args.args[1])
        self.assertFalse(self.path.exists())

    def test_non_bark_channel_has_no_badge(self):
        cfg = {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/x"}
        _, _, post = self.run_hook(self.stop(), cfg=cfg)
        self.assertNotIn("badge", json.dumps(post.call_args.args[1]))
        self.assertFalse(self.path.exists())

    def test_session_without_id_uses_empty_key(self):
        self.run_hook({"hook_event_name": "Stop", "cwd": os.getcwd()})
        self.assertEqual(self.n(""), 1)

    def test_user_prompt_submit_resets_silently(self):
        self.run_hook(self.stop())
        self.run_hook(self.stop("s2"))
        with patch.object(ln, "load_config", side_effect=AssertionError("no config")), \
                patch.object(ln, "post", side_effect=AssertionError("no network")):
            args = ln.build_parser().parse_args(["hook"])
            out = io.StringIO()
            with patch.object(sys, "stdin", io.StringIO(json.dumps(
                    {"hook_event_name": "UserPromptSubmit", "session_id": "s1"}))), \
                    contextlib.redirect_stdout(out):
                rc = ln.cmd_hook(args)
        self.assertEqual((rc, out.getvalue()), (0, ""))
        sessions = json.loads(self.path.read_text())["sessions"]
        self.assertEqual(list(sessions), ["s2"])

    def test_user_prompt_submit_dry_run_prints_nothing(self):
        _, out, post = self.run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "s1"},
                                     extra_args=("--dry-run",))
        self.assertEqual(out, "")
        post.assert_not_called()

    def test_session_end_resets_session(self):
        self.run_hook(self.stop())
        cfg = dict(BARK_CFG, events=["Stop"])    # SessionEnd 被事件过滤掉，但仍要清零
        self.run_hook({"hook_event_name": "SessionEnd", "session_id": "s1"}, cfg=cfg)
        self.assertEqual(json.loads(self.path.read_text())["sessions"], {})

    def test_corrupt_or_oversized_file_is_empty(self):
        for content in ("{broken", "[]", '{"sessions": 3}', '{"sessions": {"a": {"n": "x"}}}',
                        '{"sessions": {"a": {"n": 1, "ts": 1}}}',
                        " " * (ln.MAX_BADGE_BYTES + 1)):
            with self.subTest(content=content[:20]):
                self.path.write_text(content)
                self.assertEqual(ln.load_badge(), {})
        self.path.write_text("{broken")
        _, _, post = self.run_hook(self.stop())
        self.assertEqual(post.call_args.args[1]["badge"], 1)

    def test_old_entries_are_dropped_on_write(self):
        old = time.time() - ln.BADGE_TTL_SECONDS - 10
        self.path.write_text(json.dumps({"sessions": {
            "old": {"n": 5, "ts": old}, "new": {"n": 1, "ts": time.time()}}}))
        self.run_hook(self.stop())
        self.assertEqual(sorted(json.loads(self.path.read_text())["sessions"]), ["new", "s1"])


class TestRecapLogging(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for p in (patch.object(ln, "CONFIG_DIR", self.dir),
                  patch.object(ln, "LOG_PATH", self.dir / "debug.log")):
            p.start()
            self.addCleanup(p.stop)

    def run_hook(self, recap_result, remaining=None):
        cfg = dict(BARK_CFG, recap={"enabled": True})
        payload = {"hook_event_name": "Stop", "session_id": "s", "cwd": os.getcwd()}
        budget = ln.Budget()
        if remaining is not None:
            budget.deadline = time.monotonic() + remaining
        with patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                patch.object(ln, "load_config", return_value=cfg), \
                patch.object(ln, "parse_for_event",
                             return_value=stats_for(assistant_text="x" * 700)), \
                patch.object(ln, "git_info", return_value={}), \
                patch.object(ln, "generate_recap", return_value=recap_result), \
                patch.object(ln, "post", return_value=(True, "ok")):
            ln._run_hook(ln.build_parser().parse_args(["hook"]), budget)
        log = self.dir / "debug.log"
        return log.read_text() if log.exists() else ""

    def test_failure_logged_without_debug(self):
        self.assertIn("recap FAIL: HTTP 401", self.run_hook((None, "HTTP 401")))

    def test_success_not_logged_without_debug(self):
        self.assertNotIn("recap", self.run_hook(("摘要", "")))

    def test_budget_skip_logged(self):
        self.assertIn("recap skip: 预算不足", self.run_hook((None, "x"), remaining=3))


if __name__ == "__main__":
    unittest.main()
