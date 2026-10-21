# -*- coding: utf-8 -*-
"""Bark（iOS 推送）。走 POST /push，device_key 放在 JSON 里而不是 URL 路径里。

正文走 Bark 的 markdown 参数（App 端渲染粗体、代码块、标题、列表等，传了它 body 会被忽略）。
字段（每行两个）和脚注放进正文末尾的引用块，App 里显示为浅灰色，不和正文抢视线。
不用 subtitle：它和正文同字号，字段一多就折成好几行，反而压过正文。

Bark 的渲染器会把标题、列表行尾的硬换行再算成一个空行，所以只在「文字行后面紧跟文字行」
时补硬换行。APNs 负载上限 4KB，所以正文同时按字符数和 UTF-8 字节数截断。
自建服务用 server 指定地址，并需要在用户配置的 allowed_hosts 里放行该主机。
badge 是 App 图标上的未读计数，由上层按会话累计后放进 Message；目的地里写 "badge": false 可关闭。
icon 是可选的通知图标地址，由 App 下载（iOS 15+），不经过本插件，所以不受 allowed_hosts 限制。
"""

from __future__ import annotations

import re

from .base import Channel, Message, _is_fence, check_code, md_to_plain, truncate, truncate_md

DEFAULT_SERVER = "https://api.day.app"
MAX_BODY = 1000
MAX_BODY_BYTES = 2800    # 给标题、副标题和 APNs 外壳留出余量，整体不超过 4KB
MAX_TAIL = 400           # 末尾引用块（字段 + 脚注）的上限，正文至少留 600 字
FIELDS_PER_LINE = 2
_KEY_RE = re.compile(r"[A-Za-z0-9]+")
_ICON_RE = re.compile(r"https?://\S+")
_BLOCK_RE = re.compile(r"\s{0,3}(#{1,6}\s|[-*+]\s|\d+[.)]\s|>)")
_LABEL_RE = re.compile(r"\*\*[^*\n]+\*\*")


def _is_text(line: str) -> bool:
    return bool(line.strip()) and not _is_fence(line) and not _BLOCK_RE.match(line)


def soft_breaks(text: str) -> str:
    """文字行后面紧跟文字行（或引用行紧跟引用行）时补硬换行；标题、列表、代码块原样不动。"""
    lines = text.split("\n")
    out = []
    in_fence = False
    for i, line in enumerate(lines):
        if _is_fence(line):
            in_fence = not in_fence
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        quote = line.startswith(">") and nxt.startswith(">")
        if not in_fence and ((_is_text(line) and _is_text(nxt)) or quote):
            line = line.rstrip() + "  "
        out.append(line)
    return "\n".join(out)


def space_block(block: str) -> str:
    """分节标签（整行粗体）和它的内容之间空一行，手机上一眼分得清标签和正文。"""
    head, sep, rest = block.strip().partition("\n")
    if sep and _LABEL_RE.fullmatch(head.strip()):
        return head + "\n\n" + rest.strip()
    return block.strip()


def fit_markdown(text: str, limit: int, max_bytes: int) -> str:
    """truncate_md 只按字符数截断；中文和 emoji 占多个字节，这里再逐步收紧到字节上限内。"""
    out = truncate_md(text, limit)
    while limit > 0 and len(out.encode("utf-8")) > max_bytes:
        limit -= 50
        out = truncate_md(text, max(limit, 0))
    return out


def _field(k: str, v: str) -> str:
    return "%s: %s" % (md_to_plain(k), md_to_plain(v))


class BarkChannel(Channel):
    name = "bark"
    label = "Bark"
    default_hosts = ("api.day.app",)
    required = ("device_key",)
    optional = ("server", "icon", "badge")

    def render(self, msg: Message) -> dict:
        title = truncate(md_to_plain(msg.title), 200).replace("\n", " ")
        pairs = [msg.fields[i:i + FIELDS_PER_LINE] for i in range(0, len(msg.fields), FIELDS_PER_LINE)]
        meta = [truncate(" · ".join(_field(k, v) for k, v in p), 150) for p in pairs]
        if msg.footer:
            meta.append(truncate(md_to_plain(msg.footer), 100))
        tail = soft_breaks(truncate("\n".join("> " + m.replace("\n", " ") for m in meta), MAX_TAIL))
        # 分节之间、标签与内容之间都留一个空行，Bark 里才不会挤成一团；其余渠道仍用单换行的 body
        text = ("\n\n".join(space_block(b) for b in msg.blocks if b.strip())
                if msg.blocks else msg.body.strip())
        body = fit_markdown(soft_breaks(text), max(MAX_BODY - len(tail) - 2, 0),
                            max(MAX_BODY_BYTES - len(tail.encode("utf-8")) - 2, 0))
        out = {"title": title, "markdown": "\n\n".join(p for p in (body, tail) if p),
               "group": "Claude Code"}
        if isinstance(msg.badge, int) and not isinstance(msg.badge, bool) and msg.badge > 0:
            out["badge"] = msg.badge
        return out

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        key = dest.get("device_key") or ""
        if not _KEY_RE.fullmatch(key):
            raise ValueError("device_key 格式非法")
        server = dest.get("server") or DEFAULT_SERVER
        body = dict(body)
        body["device_key"] = key
        if dest.get("badge") is False:
            body.pop("badge", None)
        icon = dest.get("icon")
        if icon:
            if not isinstance(icon, str) or not _ICON_RE.fullmatch(icon):
                raise ValueError("icon 必须是 http(s) 图片地址")
            body["icon"] = icon
        return server.rstrip("/") + "/push", body

    def check(self, status, parsed, raw):
        return check_code(parsed, ("code",), 200, {}, "Bark")


CHANNEL = BarkChannel()
