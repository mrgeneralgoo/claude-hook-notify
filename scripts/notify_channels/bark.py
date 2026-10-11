# -*- coding: utf-8 -*-
"""Bark（iOS 推送）。走 POST /push，device_key 放在 JSON 里而不是 URL 路径里。

正文走 Bark 的 markdown 参数（App 端渲染粗体、代码块、标题、列表等，传了它 body 会被忽略），
字段放进 subtitle 显示在标题下方，脚注作为正文最后一行。单个换行转成硬换行，免得被合并成一段。
APNs 负载上限 4KB，所以正文同时按字符数和 UTF-8 字节数截断。自建服务用 server 指定地址，
并需要在用户配置的 allowed_hosts 里放行该主机。
"""

from __future__ import annotations

import re

from .base import Channel, Message, check_code, md_to_plain, truncate, truncate_md
from .dingtalk import hard_breaks

DEFAULT_SERVER = "https://api.day.app"
MAX_BODY = 1000
MAX_BODY_BYTES = 2800    # 给标题、副标题和 APNs 外壳留出余量，整体不超过 4KB
_KEY_RE = re.compile(r"[A-Za-z0-9]+")


def fit_markdown(text: str, limit: int, max_bytes: int) -> str:
    """truncate_md 只按字符数截断；中文和 emoji 占多个字节，这里再逐步收紧到字节上限内。"""
    out = truncate_md(text, limit)
    while limit > 0 and len(out.encode("utf-8")) > max_bytes:
        limit -= 50
        out = truncate_md(text, max(limit, 0))
    return out


class BarkChannel(Channel):
    name = "bark"
    label = "Bark"
    default_hosts = ("api.day.app",)
    required = ("device_key",)
    optional = ("server",)

    def render(self, msg: Message) -> dict:
        title = truncate(md_to_plain(msg.title), 200).replace("\n", " ")
        subtitle = truncate(" · ".join("%s: %s" % (md_to_plain(k), md_to_plain(v))
                                       for k, v in msg.fields), 150).replace("\n", " ")
        foot = truncate(md_to_plain(msg.footer), 100)
        body = hard_breaks(msg.body.strip()) if msg.body.strip() else ""
        body = fit_markdown(body, max(MAX_BODY - len(foot) - 2, 0),
                            max(MAX_BODY_BYTES - len(foot.encode("utf-8")) - 2, 0))
        out = {"title": title, "markdown": "\n\n".join(p for p in (body, foot) if p),
               "group": "Claude Code"}
        if subtitle:
            out["subtitle"] = subtitle
        return out

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
