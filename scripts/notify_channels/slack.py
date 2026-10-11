# -*- coding: utf-8 -*-
"""Slack Incoming Webhook，用 Block Kit 渲染。

Slack 的 mrkdwn 和通用 markdown 不同（*粗体*、<url|文字>、不支持标题），转换在
base.md_to_slack 里做。注意响应不是 JSON，而是 HTTP 200 + 纯文本 "ok"。
Block Kit 顶层 blocks 没有颜色可设（色条只属于旧版 attachments），所以不映射 status。
"""

from __future__ import annotations

from .base import Channel, Message, md_to_slack, normalize_code, truncate, truncate_md

HEADER_MAX = 150
SECTION_MAX = 3000
FIELD_MAX = 2000
FIELDS_MAX = 10


class SlackChannel(Channel):
    name = "slack"
    label = "Slack"
    default_hosts = ("hooks.slack.com",)
    required = ("webhook_url",)

    def render(self, msg: Message) -> dict:
        title = truncate(msg.title, HEADER_MAX).replace("\n", " ")
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}}]
        body = truncate_md(md_to_slack(msg.body), SECTION_MAX)
        if body:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})
        fields = [{"type": "mrkdwn",
                   "text": truncate("*%s*\n%s" % (md_to_slack(k), md_to_slack(v) or "-"), FIELD_MAX)}
                  for k, v in msg.fields[:FIELDS_MAX]]
        if fields:
            blocks.append({"type": "section", "fields": fields})
        footer = truncate(md_to_slack(msg.footer), SECTION_MAX)
        if footer:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
        return {"text": title, "blocks": blocks}

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        return dest.get("webhook_url") or "", body

    def check(self, status, parsed, raw):
        if status == 200 and isinstance(raw, str) and raw.strip() == "ok":
            return True, "ok"
        code = normalize_code(status)
        if code is None:
            return False, "Slack 响应异常（正文已省略）"
        return False, "Slack 返回 HTTP %d（正文已省略）" % code


CHANNEL = SlackChannel()
