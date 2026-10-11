# -*- coding: utf-8 -*-
"""Bark（iOS 推送）。走 POST /push，device_key 放在 JSON 里而不是 URL 路径里。

Bark 正文是纯文本，所以 markdown 降级成纯文本；字段和脚注作为附加行，整体限制在
约 1000 字符内（通知栏本来也放不下更多）。自建服务用 server 指定地址，
并需要在用户配置的 allowed_hosts 里放行该主机。
"""

from __future__ import annotations

import re

from .base import Channel, Message, check_code, md_to_plain, truncate

DEFAULT_SERVER = "https://api.day.app"
MAX_BODY = 1000
_KEY_RE = re.compile(r"[A-Za-z0-9]+")


class BarkChannel(Channel):
    name = "bark"
    label = "Bark"
    default_hosts = ("api.day.app",)
    required = ("device_key",)
    optional = ("server",)

    def render(self, msg: Message) -> dict:
        title = truncate(md_to_plain(msg.title), 200).replace("\n", " ")
        tail = "\n".join("%s: %s" % (truncate(md_to_plain(k), 30), truncate(md_to_plain(v), 100))
                         for k, v in msg.fields)
        if msg.footer:
            foot = truncate(md_to_plain(msg.footer), 100)
            tail = tail + "\n" + foot if tail else foot
        budget = max(MAX_BODY - len(tail) - 2, 0)
        body = truncate(md_to_plain(msg.body), budget)
        text = "\n".join(p for p in (body, tail) if p)
        return {"title": title, "body": truncate(text, MAX_BODY), "group": "Claude Code"}

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        key = dest.get("device_key") or ""
        if not _KEY_RE.fullmatch(key):
            raise ValueError("device_key 格式非法")
        server = dest.get("server") or DEFAULT_SERVER
        body = dict(body)
        body["device_key"] = key
        return server.rstrip("/") + "/push", body

    def check(self, status, parsed, raw):
        return check_code(parsed, ("code",), 200, {}, "Bark")


CHANNEL = BarkChannel()
