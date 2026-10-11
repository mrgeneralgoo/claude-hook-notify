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

from dataclasses import dataclass, field

# 状态 → (图标, 中文)。颜色等视觉映射属于各渠道自己的事。
# subtask / ended 只在 hook 内部使用，不对 send 的 -s 开放。
STATUSES = {
    "success": ("✅", "成功"),
    "failed": ("❌", "失败"),
    "running": ("⏳", "进行中"),
    "decision": ("🤔", "待决策"),
    "warning": ("⚠️", "警告"),
    "error": ("⚠️", "异常"),
    "info": ("💬", "信息"),
    "subtask": ("📦", "子任务"),
    "ended": ("👋", "结束"),
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
