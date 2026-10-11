# -*- coding: utf-8 -*-
"""Telegram Bot API sendMessage。

为什么发纯文本而不用 parse_mode：MarkdownV2 / HTML 要求转义一长串特殊字符，
Claude 的回复里只要漏转义一个，Telegram 就整条拒收。纯文本永远不会因格式被拒。
bot_token 会拼进 URL 路径，所以必须先校验格式，防止 token 里夹带 / ? # 改写请求目标。
"""

from __future__ import annotations

import re

from .base import Channel, Message, md_to_plain, normalize_code, truncate

MAX_CHARS = 4096
_TOKEN_RE = re.compile(r"\d+:[A-Za-z0-9_-]+")
_CHAT_RE = re.compile(r"-?\d+|@[A-Za-z0-9_]{5,}")


class TelegramChannel(Channel):
    name = "telegram"
    label = "Telegram"
    default_hosts = ("api.telegram.org",)
    required = ("bot_token", "chat_id")

    def render(self, msg: Message) -> dict:
        head = truncate(md_to_plain(msg.title), 200).replace("\n", " ")
        tail = "\n".join("%s: %s" % (truncate(md_to_plain(k), 50), truncate(md_to_plain(v), 300))
                         for k, v in msg.fields)
        if msg.footer:
            foot = truncate(md_to_plain(msg.footer), 200)
            tail = tail + "\n" + foot if tail else foot
        budget = max(MAX_CHARS - len(head) - len(tail) - 4, 0)
        body = truncate(md_to_plain(msg.body), budget)
        text = "\n\n".join(p for p in (head, body, tail) if p)
        return {"text": truncate(text, MAX_CHARS), "disable_web_page_preview": True}

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        token = dest.get("bot_token") or ""
        chat_id = dest.get("chat_id") or ""
        if not _TOKEN_RE.fullmatch(token):
            raise ValueError("bot_token 格式非法")
        if not _CHAT_RE.fullmatch(chat_id):
            raise ValueError("chat_id 格式非法")
        body = dict(body)
        body["chat_id"] = chat_id
        return "https://api.telegram.org/bot%s/sendMessage" % token, body

    def check(self, status, parsed, raw):
        if isinstance(parsed, dict) and parsed.get("ok") is True:
            return True, "ok"
        if isinstance(parsed, dict):
            code = normalize_code(parsed.get("error_code"))
            if code is not None:
                return False, "Telegram 返回 error_code=%d（含义参见 Bot API 文档）" % code
        return False, "Telegram 发送失败（正文已省略）"


CHANNEL = TelegramChannel()
