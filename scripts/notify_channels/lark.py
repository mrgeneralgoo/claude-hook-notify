# -*- coding: utf-8 -*-
"""飞书 / Lark 自定义机器人。卡片用 schema 2.0，详见 docs/DESIGN.md。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from .base import Channel, Message, check_code

# 状态 → 飞书卡片 header 颜色
STATUS_COLORS = {
    "success": "green",
    "failed": "red",
    "running": "blue",
    "decision": "red",
    "warning": "yellow",
    "error": "carmine",
    "info": "wathet",
    "subtask": "turquoise",
    "ended": "grey",
}

VALID_COLORS = {
    "blue", "wathet", "turquoise", "green", "yellow", "orange",
    "red", "carmine", "violet", "purple", "indigo", "grey",
}

# 只收录亲自验证过含义的码；其余一律只报数字，不猜、也不回显远端文案。
KNOWN_ERROR_CODES = {
    19021: "签名校验失败，或时间戳超出 1 小时（检查 secret 是否与机器人一致）",
}


def field(label: str, value: str, short: bool = True) -> dict:
    return {
        "is_short": short,
        "text": {"tag": "lark_md", "content": "**%s**\n%s" % (label, value or "-")},
    }


def build_card(title: str, color: str, body: str, fields: list[dict], footer: str) -> dict:
    """构建飞书卡片（schema 2.0）。

    为什么用 2.0 而不是 v1：v1 的正文是 `div` + `lark_md`，而 lark_md 只支持
    粗体、行内代码、链接这一小撮语法 —— Claude 回复里常见的标题（##）、列表、
    代码块、引用统统会以原文形式露出来。2.0 的 `markdown` 元素支持完整得多。

    2.0 的几个坑（都是对着真实 API 试出来的）：
      - `note` 元素**不被接受**（code 11246），无论 elements 里放 plain_text、
        markdown 还是 text，也无论换成 `text` 字段。脚注只能用 markdown 元素代替。
      - `hr`、`div`（含 fields 写法）、`column_set` 在 2.0 里仍然可用。
      - 元素挂在 `body.elements` 下，不再是顶层 `elements`。
    """
    elements: list[dict] = [{"tag": "markdown", "content": body or "-"}]
    if fields:
        elements.append({"tag": "hr"})
        # fields 是 div 独有的能力，2.0 里依然有效；它只需要粗体，lark_md 够用
        elements.append({"tag": "div", "fields": fields})
    elements.append({"tag": "markdown",
                     "content": "<font color='grey'>%s</font>" % footer})
    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color if color in VALID_COLORS else "blue",
            },
            "body": {"elements": elements},
        },
    }


def sign(secret: str, timestamp: str) -> str:
    """飞书自定义机器人签名校验：以 '<timestamp>\\n<secret>' 为 key，空串为消息体。"""
    string_to_sign = "%s\n%s" % (timestamp, secret)
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class LarkChannel(Channel):
    name = "lark"
    label = "飞书 / Lark"
    default_hosts = ("open.feishu.cn", "open.larksuite.com", "open.f.mioffice.cn")
    required = ("webhook_url",)
    optional = ("secret",)

    def render(self, msg: Message) -> dict:
        color = msg.color or STATUS_COLORS.get(msg.status, "blue")
        return build_card(msg.title, color, msg.body,
                          [field(k, v) for k, v in msg.fields], msg.footer)

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        body = dict(body)
        secret = dest.get("secret") or ""
        if secret:
            ts = str(int(time.time()))
            body["timestamp"] = ts
            body["sign"] = sign(secret, ts)
        return dest.get("webhook_url") or "", body

    def check(self, status, parsed, raw):
        return check_code(parsed, ("code", "StatusCode"), 0, KNOWN_ERROR_CODES, "飞书")


CHANNEL = LarkChannel()
