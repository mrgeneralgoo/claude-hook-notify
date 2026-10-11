#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多渠道（飞书 / 企业微信 / 钉钉 / Slack / Telegram / Bark）测试。只用标准库。"""

import base64
import hashlib
import hmac
import json
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import notify as ln  # noqa: E402
from notify_channels import CHANNELS, base, bark, dingtalk, slack, telegram, wecom  # noqa: E402
from notify_channels.base import Message  # noqa: E402
from test_notify import ConfigSandbox  # noqa: E402

TOKEN = "123456:ABC-def_GHI"
SECRET_URL = "https://x/hook/SECRET-TOKEN-123456"

DESTS = {
    "lark": {"channel": "lark", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/abc"},
    "wecom": {"channel": "wecom",
              "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc"},
    "dingtalk": {"channel": "dingtalk",
                 "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=abc"},
    "slack": {"channel": "slack", "webhook_url": "https://hooks.slack.com/services/T/B/x"},
    "telegram": {"channel": "telegram", "bot_token": TOKEN, "chat_id": "-100123"},
    "bark": {"channel": "bark", "device_key": "abc123"},
}


def sample_message(**kw):
    args = dict(
        title="✅ 构建完成 · 示例项目",
        body="**粗体** 与 `code`\n\n## 小标题\n独特短语ZEBRA-42 [文档](https://example.com/a?b=1&c=2)",
        status="success",
        fields=[("项目", "alpha"), ("分支", "feature/x"), ("主机", "mac-mini")],
        footer="Claude Code · 2026-01-02 03:04:05",
    )
    args.update(kw)
    return Message(**args)


class TestRegistry(unittest.TestCase):
    def test_exactly_six_channels(self):
        self.assertEqual(set(CHANNELS), {"lark", "wecom", "dingtalk", "slack", "telegram", "bark"})

    def test_each_channel_has_metadata(self):
        for name, ch in CHANNELS.items():
            self.assertEqual(ch.name, name)
            self.assertTrue(ch.label)
            self.assertTrue(ch.default_hosts)
            self.assertTrue(ch.required)

    def test_new_credentials_are_protected_destination_keys(self):
        for key in ("bot_token", "chat_id", "device_key", "server", "secret", "webhook_url"):
            self.assertIn(key, ln.DESTINATION_KEYS)


class TestSameMessageEveryChannel(unittest.TestCase):
    """[核心] 同一条 Message 换渠道，内容一个都不能少。"""

    def test_all_content_survives_in_every_channel(self):
        msg = sample_message()
        for name, ch in CHANNELS.items():
            payload = ch.render(msg)
            text = json.dumps(payload, ensure_ascii=False)
            for needle in ("构建完成", "示例项目", "独特短语ZEBRA-42", "小标题",
                           "项目", "alpha", "分支", "feature/x", "主机", "mac-mini",
                           "Claude Code · 2026-01-02 03:04:05"):
                self.assertIn(needle, text, "%s 丢了 %r" % (name, needle))

    def test_every_status_renders(self):
        for status in base.STATUSES:
            for name, ch in CHANNELS.items():
                json.dumps(ch.render(sample_message(status=status)))

    def test_empty_optional_parts_render(self):
        msg = Message(title="只有标题")
        for name, ch in CHANNELS.items():
            self.assertIn("只有标题", json.dumps(ch.render(msg), ensure_ascii=False), name)

    def test_color_hint_is_ignored_by_non_lark(self):
        a = sample_message(color="red")
        b = sample_message(color="")
        for name in ("wecom", "dingtalk", "slack", "telegram", "bark"):
            ch = CHANNELS[name]
            self.assertEqual(ch.render(a), ch.render(b), name)


class TestHugeBody(unittest.TestCase):
    def test_huge_body_within_platform_limits(self):
        body = ("很长的一段中文回复 with `code` and **bold**\n" * 8000)  # 远超 200KB
        msg = sample_message(body=body)
        self.assertGreater(len(body.encode("utf-8")), 200_000)
        w = wecom.CHANNEL.render(msg)["markdown"]["content"]
        self.assertLessEqual(len(w.encode("utf-8")), 4096)
        self.assertIn("Claude Code · 2026", w)          # 脚注没有被截掉
        d = dingtalk.CHANNEL.render(msg)["markdown"]["text"]
        self.assertLessEqual(len(d), 5000)
        self.assertIn("Claude Code · 2026", d)
        s = slack.CHANNEL.render(msg)
        for blk in s["blocks"]:
            if blk["type"] == "header":
                self.assertLessEqual(len(blk["text"]["text"]), 150)
            elif "text" in blk:
                self.assertLessEqual(len(blk["text"]["text"]), 3000)
            if "fields" in blk:
                self.assertLessEqual(len(blk["fields"]), 10)
                for f in blk["fields"]:
                    self.assertLessEqual(len(f["text"]), 2000)
        t = telegram.CHANNEL.render(msg)["text"]
        self.assertLessEqual(len(t), 4096)
        self.assertIn("Claude Code · 2026", t)
        b = bark.CHANNEL.render(msg)
        self.assertLessEqual(len(b["markdown"]), 1000)
        self.assertIn("Claude Code · 2026", b["markdown"])
        self.assertEqual(b["markdown"].count("```") % 2, 0)
        # 整个推送要能塞进 APNs 的 4KB 负载
        self.assertLess(len(json.dumps(b, ensure_ascii=False).encode()), 3800)

    def test_huge_fields_and_title_still_within_limits(self):
        msg = sample_message(title="T" * 5000, fields=[("L" * 500, "V" * 9000)] * 30,
                             footer="F" * 9000)
        self.assertLessEqual(len(wecom.CHANNEL.render(msg)["markdown"]["content"].encode()), 4096)
        self.assertLessEqual(len(dingtalk.CHANNEL.render(msg)["markdown"]["text"]), 5000)
        self.assertLessEqual(len(telegram.CHANNEL.render(msg)["text"]), 4096)
        b = bark.CHANNEL.render(msg)
        self.assertLessEqual(len(b["markdown"]), 1000)
        self.assertLessEqual(len(b["subtitle"]), 150)
        self.assertLess(len(json.dumps(b, ensure_ascii=False).encode()), 3800)
        blocks = slack.CHANNEL.render(msg)["blocks"]
        self.assertLessEqual(len(blocks[0]["text"]["text"]), 150)

    def test_wecom_byte_truncation_never_splits_a_character(self):
        out = base.truncate_bytes("中" * 5000, 4096)
        out.encode("utf-8")            # 不抛
        self.assertLessEqual(len(out.encode("utf-8")), 4096)
        self.assertEqual(base.truncate_bytes("short", 4096), "short")

    def test_truncated_code_fence_is_closed(self):
        text = "```\n" + "x\n" * 5000
        out = base.truncate_md(text, 500)
        self.assertLessEqual(len(out), 500)
        self.assertEqual(out.count("```") % 2, 0)


class TestMarkdownConversion(unittest.TestCase):
    def test_plain(self):
        out = base.md_to_plain("## 标题\n**粗** `c` [t](https://e.com/x)\n```py\nprint(1)\n```")
        self.assertEqual(out, "标题\n粗 c t (https://e.com/x)\nprint(1)")

    def test_slack_mrkdwn(self):
        out = base.md_to_slack("## 标题\n**粗** [t](https://e.com/?a=1&b=2) <b> & ok")
        self.assertEqual(out, "*标题*\n*粗* <https://e.com/?a=1&amp;b=2|t> &lt;b&gt; &amp; ok")

    def test_slack_code_fence_kept_and_escaped(self):
        out = base.md_to_slack("```\na < b **x**\n```")
        self.assertEqual(out, "```\na &lt; b **x**\n```")

    def test_slack_quote_keeps_marker(self):
        self.assertEqual(base.md_to_slack("> 引用 <x>"), "> 引用 &lt;x&gt;")

    def test_dingtalk_hard_breaks_outside_fences_only(self):
        out = dingtalk.hard_breaks("a\nb\n```\nc\nd\n```\ne")
        self.assertEqual(out, "a  \nb  \n```\nc\nd\n```\ne  ")


class TestWecom(unittest.TestCase):
    def test_request_url_as_is(self):
        dest = DESTS["wecom"]
        url, body = wecom.CHANNEL.request(dest, {"a": 1})
        self.assertEqual(url, dest["webhook_url"])
        self.assertEqual(body, {"a": 1})
        self.assertEqual(urllib.parse.urlsplit(url).hostname, wecom.CHANNEL.default_hosts[0])

    def test_payload_shape_and_font_color(self):
        p = wecom.CHANNEL.render(sample_message(status="success"))
        self.assertEqual(p["msgtype"], "markdown")
        self.assertIn('<font color="info">', p["markdown"]["content"])
        p = wecom.CHANNEL.render(sample_message(status="failed"))
        self.assertIn('<font color="warning">', p["markdown"]["content"])


class TestDingtalk(unittest.TestCase):
    def test_no_secret_url_unchanged(self):
        dest = DESTS["dingtalk"]
        url, _ = dingtalk.CHANNEL.request(dest, {})
        self.assertEqual(url, dest["webhook_url"])

    def test_signature_recomputed(self):
        dest = dict(DESTS["dingtalk"], secret="SEC-key")
        url, _ = dingtalk.CHANNEL.request(dest, {})
        parts = urllib.parse.urlsplit(url)
        self.assertEqual(parts.hostname, "oapi.dingtalk.com")
        q = urllib.parse.parse_qs(parts.query)
        self.assertEqual(q["access_token"], ["abc"])
        ts = q["timestamp"][0]
        self.assertEqual(len(ts), 13)
        expect = base64.b64encode(hmac.new(b"SEC-key", ("%s\nSEC-key" % ts).encode(),
                                           hashlib.sha256).digest()).decode()
        self.assertEqual(q["sign"], [expect])      # parse_qs 已做 URL 解码

    def test_signature_without_existing_query_uses_question_mark(self):
        dest = {"webhook_url": "https://oapi.dingtalk.com/robot/send", "secret": "s"}
        url, _ = dingtalk.CHANNEL.request(dest, {})
        self.assertIn("/robot/send?timestamp=", url)

    def test_title_is_plain_and_text_has_hard_breaks(self):
        p = dingtalk.CHANNEL.render(sample_message(body="第一行\n第二行"))
        self.assertEqual(p["markdown"]["title"], "✅ 构建完成 · 示例项目")
        self.assertIn("第一行  \n第二行", p["markdown"]["text"])


class TestSlackRender(unittest.TestCase):
    def test_block_structure(self):
        p = slack.CHANNEL.render(sample_message())
        self.assertEqual([b["type"] for b in p["blocks"]], ["header", "section", "section", "context"])
        self.assertEqual(p["text"], "✅ 构建完成 · 示例项目")
        self.assertEqual(p["blocks"][2]["fields"][0]["text"], "*项目*\nalpha")
        self.assertIn("*粗体*", p["blocks"][1]["text"]["text"])
        self.assertIn("<https://example.com/a?b=1&amp;c=2|文档>", p["blocks"][1]["text"]["text"])

    def test_at_most_ten_fields(self):
        p = slack.CHANNEL.render(sample_message(fields=[("k%d" % i, "v") for i in range(25)]))
        self.assertEqual(len(p["blocks"][2]["fields"]), 10)


class TestTelegram(unittest.TestCase):
    def test_request_token_in_path(self):
        url, body = telegram.CHANNEL.request(DESTS["telegram"], {"text": "hi"})
        self.assertEqual(url, "https://api.telegram.org/bot%s/sendMessage" % TOKEN)
        self.assertEqual(urllib.parse.urlsplit(url).hostname, "api.telegram.org")
        self.assertEqual(body["chat_id"], "-100123")
        self.assertEqual(body["text"], "hi")

    def test_no_parse_mode_and_plain_text(self):
        p = telegram.CHANNEL.render(sample_message())
        self.assertNotIn("parse_mode", p)
        self.assertTrue(p["disable_web_page_preview"])
        self.assertNotIn("**", p["text"])
        self.assertIn("文档 (https://example.com/a?b=1&c=2)", p["text"])

    def test_username_chat_id_ok(self):
        telegram.CHANNEL.request(dict(DESTS["telegram"], chat_id="@my_channel"), {})

    def test_malformed_credentials_raise_without_leaking(self):
        bad_tokens = ["12:ab/../x", "12:ab?x=1", "abc", "12:ab\n", "12:", ":ab", "12:ab#c", "12:a b"]
        for tok in bad_tokens:
            with self.assertRaises(ValueError) as cm:
                telegram.CHANNEL.request(dict(DESTS["telegram"], bot_token=tok), {})
            self.assertNotIn("ab", str(cm.exception).replace("bot_token", ""))
        for chat in ["abc", "@ab", "12 3", "1\n", "-", "@bad-name1", "1/2"]:
            with self.assertRaises(ValueError):
                telegram.CHANNEL.request(dict(DESTS["telegram"], chat_id=chat), {})

    def test_error_message_has_no_token(self):
        with self.assertRaises(ValueError) as cm:
            telegram.CHANNEL.request(dict(DESTS["telegram"], bot_token="9:bad/token"), {})
        self.assertNotIn("bad/token", str(cm.exception))
        ok, why, _, _ = ln.prepare_request(dict(DESTS["telegram"], bot_token="9:bad/token"), {})
        self.assertFalse(ok)
        self.assertNotIn("bad/token", why)


class TestBark(unittest.TestCase):
    def test_default_server(self):
        url, body = bark.CHANNEL.request(DESTS["bark"], {"title": "t"})
        self.assertEqual(url, "https://api.day.app/push")
        self.assertEqual(body["device_key"], "abc123")
        self.assertEqual(body["title"], "t")

    def test_group_in_render(self):
        self.assertEqual(bark.CHANNEL.render(sample_message())["group"], "Claude Code")

    def test_markdown_and_subtitle(self):
        out = bark.CHANNEL.render(sample_message(body="**粗体**\n第二行\n```\ncode\n```"))
        self.assertNotIn("body", out)                       # 传了 markdown，body 会被 Bark 忽略
        self.assertIn("**粗体**  \n第二行\n```\ncode\n```", out["markdown"])
        # 前两个字段进副标题，其余字段和脚注进末尾的灰色引用块
        self.assertEqual(out["subtitle"], "项目: alpha · 分支: feature/x")
        self.assertTrue(out["markdown"].endswith(
            "\n\n> 主机: mac-mini  \n> Claude Code · 2026-01-02 03:04:05"))

    def test_hard_breaks_only_between_text_lines(self):
        src = "## 标题\n- a\n- b\n文字一\n文字二\n> 引用"
        self.assertEqual(bark.soft_breaks(src), "## 标题\n- a\n- b\n文字一  \n文字二\n> 引用")

    def test_no_fields_no_subtitle(self):
        self.assertNotIn("subtitle", bark.CHANNEL.render(Message(title="t", body="b")))

    def test_multibyte_body_capped_by_bytes(self):
        out = bark.CHANNEL.render(sample_message(body="😀" * 2000))
        self.assertLessEqual(len(out["markdown"].encode()), bark.MAX_BODY_BYTES)

    def test_custom_server_honored(self):
        dest = dict(DESTS["bark"], server="https://bark.example.com/")
        url, _ = bark.CHANNEL.request(dest, {})
        self.assertEqual(url, "https://bark.example.com/push")
        ok, why, _, _ = ln.prepare_request(dest, {})
        self.assertFalse(ok)                                  # 默认白名单不放行
        self.assertIn("bark.example.com", why)
        ok, why, _, _ = ln.prepare_request(dest, {}, ("bark.example.com",))
        self.assertTrue(ok, why)

    def test_invalid_device_key_raises(self):
        for key in ("a/b", "a b", "abc\n", "a?b", "../x", "ab-cd"):
            with self.assertRaises(ValueError, msg=key):
                bark.CHANNEL.request(dict(DESTS["bark"], device_key=key), {})


class TestDefaultHosts(unittest.TestCase):
    def test_typical_dest_passes_host_allowlist(self):
        for name, dest in DESTS.items():
            ok, why, url, _ = ln.prepare_request(dest, {})
            self.assertTrue(ok, "%s: %s" % (name, why))
            self.assertIn(urllib.parse.urlsplit(url).hostname, CHANNELS[name].default_hosts)

    def test_missing_required_field_reported_by_name(self):
        ok, why, _, _ = ln.prepare_request({"channel": "telegram", "bot_token": TOKEN}, {})
        self.assertFalse(ok)
        self.assertIn("chat_id", why)
        self.assertNotIn(TOKEN, why)


class TestCheckNeverLeaks(unittest.TestCase):
    """[高危] check() 的说明里不得出现任何远端文本。"""

    def hostile_responses(self):
        planted = {"errcode": 310000, "code": 400, "errmsg": SECRET_URL, "msg": SECRET_URL,
                   "message": SECRET_URL, "description": SECRET_URL, "ok": False,
                   "error_code": 400}
        return [
            (400, planted, json.dumps(planted)),
            (200, planted, json.dumps(planted)),
            (502, None, "<html>bad gateway for %s</html>" % SECRET_URL),
            (200, None, SECRET_URL),
            (200, [SECRET_URL], json.dumps([SECRET_URL])),
            (200, {"errcode": SECRET_URL, "code": SECRET_URL, "error_code": SECRET_URL},
             SECRET_URL),
            (None, None, SECRET_URL),
            (SECRET_URL, None, SECRET_URL),
        ]

    def test_no_channel_echoes_remote_text(self):
        for name, ch in CHANNELS.items():
            for status, parsed, raw in self.hostile_responses():
                ok, detail = ch.check(status, parsed, raw)
                self.assertNotIn("SECRET-TOKEN", detail, name)
                self.assertNotIn("https://x", detail, name)
                self.assertFalse(ok, "%s 把敌意响应当成成功: %r" % (name, (status, parsed)))

    def test_code_based_channels_reject_bool_float_none_missing(self):
        cases = {"wecom": "errcode", "dingtalk": "errcode", "bark": "code"}
        for name, key in cases.items():
            ch = CHANNELS[name]
            ok_val = 200 if name == "bark" else 0
            self.assertTrue(ch.check(200, {key: ok_val}, "")[0], name)
            for bad in (False, True, 0.0 if ok_val == 0 else 200.0, None, "", "ok", [], {}):
                self.assertFalse(ch.check(200, {key: bad}, "")[0], "%s %r" % (name, bad))
            self.assertFalse(ch.check(200, {}, "")[0], name)
            self.assertFalse(ch.check(200, None, "")[0], name)
            self.assertFalse(ch.check(200, [ok_val], "")[0], name)

    def test_wecom_dingtalk_report_numeric_code_only(self):
        for ch in (wecom.CHANNEL, dingtalk.CHANNEL):
            ok, detail = ch.check(200, {"errcode": 93000, "errmsg": SECRET_URL}, "")
            self.assertFalse(ok)
            self.assertIn("93000", detail)
            self.assertNotIn("SECRET", detail)

    def test_slack_success_only_for_plain_ok(self):
        ch = slack.CHANNEL
        self.assertTrue(ch.check(200, None, "ok")[0])
        self.assertTrue(ch.check(200, None, "ok\n")[0])
        for status, raw in ((200, "invalid_payload"), (200, ""), (200, "okay"),
                            (404, "ok"), (None, "ok"), (200, '{"ok": true}')):
            self.assertFalse(ch.check(status, None, raw)[0], (status, raw))
        ok, detail = ch.check(404, None, "no_service " + SECRET_URL)
        self.assertIn("404", detail)
        self.assertNotIn("SECRET", detail)

    def test_telegram_ok_must_be_literally_true(self):
        ch = telegram.CHANNEL
        self.assertTrue(ch.check(200, {"ok": True, "result": {}}, "")[0])
        for bad in (False, 1, "true", None, "yes", [True]):
            self.assertFalse(ch.check(200, {"ok": bad}, "")[0], bad)
        self.assertFalse(ch.check(200, {}, "")[0])
        self.assertFalse(ch.check(200, None, "")[0])
        self.assertFalse(ch.check(200, True, "")[0])
        ok, detail = ch.check(400, {"ok": False, "error_code": 400,
                                    "description": "Bad Request: " + SECRET_URL}, "")
        self.assertFalse(ok)
        self.assertIn("400", detail)
        self.assertNotIn("Bad Request", detail)
        self.assertNotIn("SECRET", detail)


class FakeResponse:
    """urlopen 的替身：支持 with、status、read(n)。"""

    def __init__(self, status, body):
        self.status = status
        self._body = body.encode("utf-8") if isinstance(body, str) else body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._body if n is None or n < 0 else self._body[:n]


class TestEndToEndPost(unittest.TestCase):
    """经 notify.post() 的共用传输层走一遍，验证 channel.check 的集成。"""

    def run_post(self, dest, response, hosts=None, payload=None):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["data"] = json.loads(req.data.decode("utf-8"))
            seen["ua"] = req.get_header("User-agent")
            if isinstance(response, Exception):
                raise response
            return response

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            result = ln.post(dest, payload if payload is not None else {"text": "hi"}, hosts=hosts)
        return result, seen

    def test_telegram_success_and_request_shape(self):
        payload = telegram.CHANNEL.render(sample_message())
        (ok, why), seen = self.run_post(DESTS["telegram"],
                                        FakeResponse(200, '{"ok": true, "result": {}}'),
                                        payload=payload)
        self.assertTrue(ok, why)
        self.assertEqual(seen["url"], "https://api.telegram.org/bot%s/sendMessage" % TOKEN)
        self.assertEqual(seen["data"]["chat_id"], "-100123")
        self.assertIn("独特短语ZEBRA-42", seen["data"]["text"])

    def test_telegram_failure_reports_code_not_description(self):
        body = json.dumps({"ok": False, "error_code": 401,
                           "description": "Unauthorized " + SECRET_URL})
        (ok, why), _ = self.run_post(DESTS["telegram"], FakeResponse(200, body))
        self.assertFalse(ok)
        self.assertIn("401", why)
        self.assertNotIn("SECRET", why)
        self.assertNotIn(TOKEN, why)

    def test_telegram_http_error_does_not_leak_token(self):
        err = urllib.error.HTTPError("https://api.telegram.org/bot%s/sendMessage" % TOKEN,
                                     404, "Not Found", {}, None)
        (ok, why), _ = self.run_post(DESTS["telegram"], err)
        self.assertFalse(ok)
        self.assertIn("404", why)
        self.assertNotIn(TOKEN, why)

    def test_slack_ok_plain_text(self):
        (ok, why), seen = self.run_post(DESTS["slack"], FakeResponse(200, "ok"),
                                        payload=slack.CHANNEL.render(sample_message()))
        self.assertTrue(ok, why)
        self.assertEqual(seen["url"], DESTS["slack"]["webhook_url"])
        self.assertEqual(seen["data"]["blocks"][0]["type"], "header")

    def test_slack_error_text_is_not_echoed(self):
        (ok, why), _ = self.run_post(DESTS["slack"], FakeResponse(200, "invalid_token " + SECRET_URL))
        self.assertFalse(ok)
        self.assertNotIn("SECRET", why)
        self.assertNotIn("invalid_token", why)

    def test_wecom_dingtalk_bark_e2e(self):
        (ok, why), _ = self.run_post(DESTS["wecom"], FakeResponse(200, '{"errcode":0,"errmsg":"ok"}'))
        self.assertTrue(ok, why)
        (ok, why), seen = self.run_post(dict(DESTS["dingtalk"], secret="s"),
                                        FakeResponse(200, '{"errcode":0,"errmsg":"ok"}'))
        self.assertTrue(ok, why)
        self.assertIn("sign=", seen["url"])
        (ok, why), seen = self.run_post(DESTS["bark"],
                                        FakeResponse(200, '{"code":200,"message":"success"}'))
        self.assertTrue(ok, why)
        self.assertEqual(seen["url"], "https://api.day.app/push")
        self.assertEqual(seen["ua"], "claude-hook-notify")   # Cloudflare 会拦 Python-urllib
        (ok, why), _ = self.run_post(DESTS["bark"], FakeResponse(200, '{"code":400,"message":"x"}'))
        self.assertFalse(ok)
        self.assertIn("400", why)

    def test_wrong_host_rejected_with_hostname_only(self):
        for dest in (DESTS["telegram"], DESTS["slack"]):
            called = []
            with mock.patch("urllib.request.urlopen", lambda *a, **k: called.append(1)):
                ok, why = ln.post(dest, {}, hosts=("example.com",))
            self.assertFalse(ok)
            self.assertEqual(called, [])
            self.assertNotIn(TOKEN, why)
            self.assertNotIn("/services/", why)
            self.assertIn(CHANNELS[dest["channel"]].default_hosts[0], why)

    def test_http_url_for_slack_rejected(self):
        dest = dict(DESTS["slack"], webhook_url="http://hooks.slack.com/services/T/B/SECRETX")
        ok, why = ln.post(dest, {})
        self.assertFalse(ok)
        self.assertNotIn("SECRETX", why)

    def test_malformed_telegram_dest_via_post_has_no_secret(self):
        dest = dict(DESTS["telegram"], bot_token="1:abc/../../evil?x=SECRETX")
        ok, why = ln.post(dest, {})
        self.assertFalse(ok)
        self.assertNotIn("SECRETX", why)


class TestConfigIntegration(ConfigSandbox):
    def load(self):
        return ln.load_config(str(self.project))

    def write_notify_project(self, data):
        (self.project / ".claude" / "notify.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_user_config_telegram(self):
        self.write_user({"channel": "telegram", "bot_token": TOKEN, "chat_id": "42"})
        cfg = self.load()
        self.assertFalse(cfg.get("_fatal"))
        self.assertEqual(ln.destination(cfg),
                         {"channel": "telegram", "bot_token": TOKEN, "chat_id": "42"})

    def test_named_destination_resolves_to_bark(self):
        self.write_user({"destinations": {"手机": {"channel": "bark", "device_key": "abc"}},
                         "destination": "手机",
                         "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/old",
                         "secret": "oldsecret"})
        cfg = self.load()
        self.assertFalse(cfg.get("_fatal"))
        self.assertEqual(ln.destination(cfg), {"channel": "bark", "device_key": "abc"})

    def test_project_config_cannot_set_destination(self):
        self.write_user({"channel": "telegram", "bot_token": TOKEN, "chat_id": "42"})
        self.write_notify_project({"channel": "bark", "bot_token": "9:evil", "device_key": "evil",
                                   "chat_id": "666", "server": "https://evil.example"})
        cfg = self.load()
        self.assertFalse(cfg.get("_fatal"))
        self.assertEqual(ln.destination(cfg),
                         {"channel": "telegram", "bot_token": TOKEN, "chat_id": "42"})
        joined = "\n".join(cfg["_warnings"])
        for key in ("channel", "bot_token", "device_key"):
            self.assertIn(key, joined)
        self.assertNotIn("9:evil", joined)

    def test_project_can_select_registered_destination_by_name(self):
        self.write_user({"destinations": {"手机": {"channel": "bark", "device_key": "abc"}},
                         "channel": "telegram", "bot_token": TOKEN, "chat_id": "42"})
        self.write_notify_project({"destination": "手机"})
        cfg = self.load()
        self.assertEqual(ln.destination(cfg), {"channel": "bark", "device_key": "abc"})

    def test_unknown_channel_is_fatal(self):
        self.write_user({"channel": "pigeon", "webhook_url": "https://open.feishu.cn/x"})
        cfg = self.load()
        self.assertTrue(cfg.get("_fatal"))

    def test_named_destination_missing_required_field_is_fatal(self):
        self.write_user({"destinations": {"tg": {"channel": "telegram", "bot_token": TOKEN}},
                         "destination": "tg"})
        cfg = self.load()
        self.assertTrue(cfg.get("_fatal"))
        self.assertNotIn(TOKEN, cfg["_fatal"])

    def test_dry_run_render_uses_selected_channel(self):
        self.write_user({"channel": "slack", "webhook_url": "https://hooks.slack.com/services/a"})
        cfg = self.load()
        payload = ln.render(cfg, sample_message())
        self.assertIn("blocks", payload)


if __name__ == "__main__":
    unittest.main()
