# -*- coding: utf-8 -*-
"""宿主契约：把各宿主的事件与会话信息转换成公共通知字段。"""

from __future__ import annotations

from typing import Callable


class Harness:
    name: str = ""
    label: str = ""
    project_dir: str = ""
    legacy_project_config: str = ""
    session_env: str = ""
    continuation_label: str = ""
    notification_icon: str = ""
    permission_details_require_summary: bool = True

    def normalize_hook(self, payload: dict) -> dict | None:
        """返回公共事件字段；None 表示跳过。来源标记由公共入口写入。"""
        return dict(payload)

    def parse_stats(self, payload: dict, transcript_reader: Callable[..., dict]) -> dict:
        raise NotImplementedError

    def session_context(self, payload: dict, stats: dict | None,
                        transcript_reader: Callable[..., dict],
                        transcript_finder: Callable[[str], str]) -> tuple[str, str]:
        """默认只用事件自带的会话 ID，不查找其他宿主的历史。"""
        return payload.get("session_id", ""), (stats or {}).get("session_name", "")

    def debug_message(self, payload: dict, raw: str) -> str:
        """默认日志只包含事件名，不包含会话内容或工具参数。"""
        return "%s hook event=%s" % (
            self.label, payload.get("_event_name", payload.get("hook_event_name")))


def reset_turn_state(stats: dict) -> None:
    """清空本轮字段和最早时间，避免摘要或耗时跨越轮次边界。"""
    stats["user_prompt"] = ""
    stats["assistant_text"] = ""
    stats["tool_calls"] = 0
    stats["turn_start"] = None
    stats["turn_kind"] = ""
    stats["earliest_ts"] = None
