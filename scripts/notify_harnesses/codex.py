# -*- coding: utf-8 -*-
"""Codex 原生生命周期 hooks；只使用稳定的事件字段。"""

from __future__ import annotations

from typing import Callable

from .base import Harness


class CodexHarness(Harness):
    name = "codex"
    label = "Codex"
    notification_icon = "https://cdn.oaistatic.com/assets/apple-touch-icon-mz9nytnj.webp"
    project_dir = ".codex"
    session_env = "CODEX_THREAD_ID"

    def normalize_hook(self, payload: dict) -> dict | None:
        event = payload.get("hook_event_name")
        if event not in ("Stop", "SubagentStop", "PermissionRequest"):
            return None
        if "stop_hook_active" in payload and not isinstance(payload["stop_hook_active"], bool):
            return None
        if event in ("Stop", "SubagentStop") and payload.get("stop_hook_active"):
            return None
        fields = {"session_id": payload.get("session_id", ""),
                  "cwd": payload.get("cwd", ""), "hook_event_name": event,
                  "last_assistant_message": payload.get("last_assistant_message")}
        if event == "PermissionRequest":
            description = payload.get("permission_description")
            tool_name = payload.get("tool_name", "")
            if (description is not None and not isinstance(description, str)) or not isinstance(tool_name, str):
                return None
            fields.update(hook_event_name="Notification", notification_type="permission_prompt",
                          message=description or tool_name, _event_name=event)
        if any(not isinstance(fields[k], str) or not fields[k].strip()
               for k in ("session_id", "cwd")):
            return None
        reply = fields["last_assistant_message"]
        if reply is not None and not isinstance(reply, str):
            return None
        return fields

    def parse_stats(self, payload: dict, transcript_reader: Callable[..., dict]) -> dict:
        return {"assistant_text": payload.get("last_assistant_message") or "",
                "summary_reliable": True}


HARNESS = CodexHarness()
