# -*- coding: utf-8 -*-
"""企业微信群机器人。用 markdown 消息：支持标题、粗体、链接、行内代码、引用和三色 <font>。

长度上限 4096 是**字节**（不是字符），中文占 3 字节，所以按字节截断。
"""

from __future__ import annotations

from .base import Channel, Message, check_code, truncate, truncate_bytes

MAX_BYTES = 4096

# 企业微信只有 info(绿) / comment(灰) / warning(橙) 三种颜色
STATUS_FONT = {
    "success": "info",
    "failed": "warning",
    "error": "warning",
    "warning": "warning",
    "decision": "warning",
    "ended": "comment",
}


class WecomChannel(Channel):
    name = "wecom"
    label = "企业微信"
    default_hosts = ("qyapi.weixin.qq.com",)
    required = ("webhook_url",)

    def render(self, msg: Message) -> dict:
        font = STATUS_FONT.get(msg.status)
        title = truncate(msg.title, 200).replace("\n", " ")
        head = "## <font color=\"%s\">%s</font>" % (font, title) if font else "## " + title
        fields = ["**%s**: %s" % (truncate(k, 50), truncate(v, 300)) for k, v in msg.fields]
        tail = "\n".join(fields)
        if msg.footer:
            foot = "<font color=\"comment\">%s</font>" % truncate(msg.footer, 200)
            tail = tail + "\n" + foot if tail else foot
        fixed = len(head.encode("utf-8")) + len(tail.encode("utf-8")) + 4
        body = truncate_bytes(msg.body, max(MAX_BYTES - fixed, 0))
        content = "\n".join(p for p in (head, body, tail) if p)
        return {"msgtype": "markdown", "markdown": {"content": truncate_bytes(content, MAX_BYTES)}}

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        return dest.get("webhook_url") or "", body

    def check(self, status, parsed, raw):
        return check_code(parsed, ("errcode",), 0, {}, "企业微信")


CHANNEL = WecomChannel()
