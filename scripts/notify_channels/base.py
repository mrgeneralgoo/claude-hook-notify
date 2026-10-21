# -*- coding: utf-8 -*-
"""渠道契约。

上层（hook / send / doctor）只产出一条与渠道无关的 Message；每个渠道负责三件事：
  render   把 Message 渲染成该渠道的请求体（格式差异全部关在这里）
  request  根据目的地配置拼出最终 URL，并完成签名等鉴权
  check    判定响应是否成功

真正的 HTTP 发送由 notify.post() 统一完成，渠道不自己发请求 ——
「错误信息里永远不出现 URL」「远端返回的文本一概不记」这两条约束只在一处实现，
新渠道不可能因为写漏而破坏它们。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 状态 → (图标, 中文)。颜色等视觉映射属于各渠道自己的事。
# subtask / ended 只在 hook 内部使用，不对 send 的 -s 开放。
STATUSES = {
    "success": ("🟢", "成功"),
    "failed": ("🔴", "失败"),
    "running": ("🔵", "进行中"),
    "decision": ("🔴", "待决策"),
    "warning": ("🟡", "警告"),
    "error": ("🔴", "异常"),
    "info": ("⚪", "信息"),
    "subtask": ("🟣", "子任务"),
    "ended": ("⚪", "结束"),
}
SEND_STATUSES = ("success", "failed", "running", "decision", "warning", "error", "info")


@dataclass
class Message:
    """一条与渠道无关的通知。

    body 用通用 markdown 书写（**粗体**、标题、列表、代码块、引用）；
    渠道不支持的语法由渠道自己降级，调用方不需要关心。
    """
    title: str
    body: str = ""
    status: str = "info"
    fields: list = field(default_factory=list)   # [(标签, 值), ...]，值可含行内 markdown
    footer: str = ""
    color: str = ""      # 渠道私有的颜色提示（目前只有 lark 认），其余渠道忽略
    # body 按分节拆开的版本；需要分节留白的渠道（目前只有 bark）用它，其余渠道用 body
    blocks: list = field(default_factory=list)
    badge: int | None = None   # 未读计数，目前只有 bark 用


class Channel:
    """渠道基类。子类只需填类属性并实现 render / request / check。"""

    name = ""                 # 配置里 "channel" 的取值
    label = ""                # 给人看的名字
    default_hosts: tuple = ()  # 允许发往的主机，用户可用 allowed_hosts 整体替换
    required: tuple = ()      # 目的地必填字段
    optional: tuple = ()      # 目的地可选字段

    @property
    def dest_keys(self) -> tuple:
        return self.required + self.optional

    def render(self, msg: Message) -> dict:
        raise NotImplementedError

    def request(self, dest: dict, body: dict) -> tuple[str, dict]:
        """返回 (最终 URL, 最终请求体)。签名、把 token 拼进 URL 都在这里做。"""
        raise NotImplementedError

    def check(self, status: int | None, parsed, raw: str) -> tuple[bool, str]:
        """判定响应。parsed 是解析后的 JSON（不是 JSON 时为 None）。

        **契约：返回的说明里绝不能包含 raw 或 parsed 里的任何远端文本** ——
        代理和错误页会把请求 URL（含 token）原样打回来。只允许状态码、数字错误码
        和渠道自己写死的静态说明。
        """
        raise NotImplementedError


def normalize_code(value) -> int | None:
    """把远端错误码规范成有限范围内的整数；不合规一律丢弃，不回显原值。

    注意 Python 里 False == 0、0.0 == 0：直接写 `raw in (0, None)` 会把
    {"code": false}、{"code": null} 乃至缺失 code 的畸形响应当成发送成功。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if -1_000_000 < value < 1_000_000 else None
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        try:
            num = int(value.strip())
        except ValueError:
            return None
        return num if -1_000_000 < num < 1_000_000 else None
    return None


def check_code(parsed, keys: tuple, ok_value: int, known: dict, brand: str) -> tuple[bool, str]:
    """「JSON 里有个数字错误码」这一类响应的通用判定。"""
    if not isinstance(parsed, dict):
        return False, "响应不是 JSON 对象（正文已省略）"
    raw_code = None
    for key in keys:
        if key in parsed:
            raw_code = parsed[key]
            break
    code = normalize_code(raw_code)
    if code is None:
        return False, "响应错误码格式非法或缺失（正文已省略）"
    if code == ok_value:
        return True, "ok"
    return False, "%s返回 code=%s（%s）" % (brand, code, known.get(code, "含义参见%s开放平台文档" % brand))


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# ── 渠道共用的纯文本 / markdown 转换（只追加，不改上面的定义） ────────────────

_FENCE = "```"
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")


def _is_fence(line: str) -> bool:
    return line.lstrip().startswith(_FENCE)


def truncate_bytes(text: str, limit: int) -> str:
    """按 UTF-8 字节数截断，不会切坏多字节字符；超长时以 … 结尾（结果 ≤ limit 字节）。"""
    text = (text or "").strip()
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    cut = raw[: max(limit - 3, 0)].decode("utf-8", "ignore").rstrip()
    return cut + "…"


def truncate_md(text: str, limit: int) -> str:
    """按字符数截断 markdown；若截断后留下未闭合的代码块，补一个收尾围栏。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = truncate(text, limit - 5)
    if sum(1 for ln in cut.split("\n") if _is_fence(ln)) % 2:
        cut += "\n" + _FENCE
    return cut


def md_to_plain(text: str) -> str:
    """通用 markdown → 可读纯文本：去掉 ** 与标题 #，保留代码内容，链接写成「文字 (地址)」。"""
    out = []
    in_fence = False
    for line in (text or "").split("\n"):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            m = _HEADING_RE.match(line)
            if m:
                line = m.group(1)
            line = _LINK_RE.sub(lambda mm: "%s (%s)" % (mm.group(1), mm.group(2)), line)
            line = _BOLD_RE.sub(r"\1", line)
            line = line.replace("`", "")
        out.append(line)
    return "\n".join(out).strip()


def md_to_slack(text: str) -> str:
    """通用 markdown → Slack mrkdwn。

    先转义 & < >（Slack 要求），再生成 <url|文字> 链接，所以生成的尖括号不会被转义。
    引用行的前导 > 要保留原样，Slack 才认作引用。代码块内只转义，不做其它转换。
    """
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    out = []
    in_fence = False
    for line in (text or "").split("\n"):
        if _is_fence(line):
            in_fence = not in_fence
            out.append(_FENCE)
            continue
        if in_fence:
            out.append(esc(line))
            continue
        quote = ""
        if line.startswith(">"):
            quote, line = "> ", line[1:].lstrip()
        m = _HEADING_RE.match(line)
        heading = m is not None
        if heading:
            line = _BOLD_RE.sub(r"\1", m.group(1))
        line = esc(line)
        line = _LINK_RE.sub(lambda mm: "<%s|%s>" % (mm.group(2), mm.group(1)), line)
        line = _BOLD_RE.sub(r"*\1*", line)
        if heading and line:
            line = "*%s*" % line
        out.append(quote + line)
    return "\n".join(out).strip()
