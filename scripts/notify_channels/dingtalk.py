# -*- coding: utf-8 -*-
"""钉钉自定义机器人（可选加签）。

钉钉 markdown 里单个换行不会换行，必须在行尾补两个空格 —— 但代码块内部不能补，
否则代码里会混进多余空格。markdown.title 只用于通知预览，所以放纯文本标题。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse

from .base import Channel, Message, _is_fence, check_code, truncate, truncate_md

MAX_CHARS = 5000


def hard_breaks(text: str) -> str:
    """把代码块之外的单个换行变成 markdown 硬换行（行尾两个空格）。"""
    out = []
    in_fence = False
    for line in text.split("\n"):
        if _is_fence(line):
            in_fence = not in_fence
            out.append(line)
        elif in_fence or not line.strip():
            out.append(line)
        else:
            out.append(line.rstrip() + "  ")
    return "\n".join(out)


def sign(secret: str, timestamp: str) -> str:
    """钉钉加签：HMAC-SHA256(key=secret, msg='<timestamp>\\n<secret>')，base64 后再 URL 编码。"""
    string_to_sign = "%s\n%s" % (timestamp, secret)
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                      hashlib.sha256).digest()
    return urllib.parse.quote_plus(base64.b64encode(digest))


class DingtalkChannel(Channel):
    name = "dingtalk"
    label = "钉钉"
    default_hosts = ("oapi.dingtalk.com",)
    required = ("webhook_url",)
    optional = ("secret",)

    def render(self, msg: Message) -> dict:
        title = truncate(msg.title, 200).replace("\n", " ")
        parts = ["### " + title]
        fields = ["**%s**: %s" % (truncate(k, 50), truncate(v, 300)) for k, v in msg.fields]
        tail = "\n".join(fields)
        if msg.footer:
            foot = truncate(msg.footer, 200)
            tail = tail + "\n" + foot if tail else foot
        tail = hard_breaks(tail)
        head = hard_breaks(parts[0])
        budget = max(MAX_CHARS - len(head) - len(tail) - 8, 0)
        body = truncate_md(hard_breaks(msg.body.strip()), budget) if msg.body.strip() else ""
        text = "\n\n".join(p for p in (head, body, tail) if p)
        return {"msgtype": "markdown",
                "markdown": {"title": title, "text": truncate_md(text, MAX_CHARS)}}

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        url = dest.get("webhook_url") or ""
        secret = dest.get("secret") or ""
        if secret:
            ts = str(round(time.time() * 1000))
            url += ("&" if "?" in url else "?") + "timestamp=%s&sign=%s" % (ts, sign(secret, ts))
        return url, body

    def check(self, status, parsed, raw):
        return check_code(parsed, ("errcode",), 0, {}, "钉钉")


CHANNEL = DingtalkChannel()
