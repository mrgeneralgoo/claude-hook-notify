# -*- coding: utf-8 -*-
"""Claude Code 的 hook、会话记录与会话标题策略。"""

from __future__ import annotations

import os
from typing import Callable

from .base import Harness, reset_turn_state


def transcript_for(payload: dict) -> tuple[str, bool]:
    """选择 Claude 事件对应的 transcript 和 subagent 解析作用域。"""
    if (payload.get("hook_event_name") or "") == "SubagentStop":
        agent_path = payload.get("agent_transcript_path") or payload.get("agentTranscriptPath") or ""
        if agent_path:
            return agent_path, True
        return payload.get("transcript_path", ""), True
    return payload.get("transcript_path", ""), False


class ClaudeHarness(Harness):
    name = "claude"
    label = "Claude Code"
    project_dir = ".claude"
    legacy_project_config = "lark.json"
    session_env = "CLAUDE_CODE_SESSION_ID"
    continuation_label = "Claude"
    permission_details_require_summary = False

    def parse_stats(self, payload: dict, transcript_reader: Callable[..., dict]) -> dict:
        event = payload.get("hook_event_name") or "Stop"
        if event == "SubagentStop":
            agent_path = payload.get("agent_transcript_path") or payload.get("agentTranscriptPath") or ""
            if agent_path:
                stats = transcript_reader(agent_path, sidechain=True)
                stats["summary_reliable"] = True
                return stats
            # 父文件可能混有并发子任务：只取元数据，不能混拼任务与回复。
            stats = transcript_reader(payload.get("transcript_path", ""), sidechain=False)
            reset_turn_state(stats)
            stats["summary_reliable"] = False
            return stats
        stats = transcript_reader(payload.get("transcript_path", ""), sidechain=False)
        stats["summary_reliable"] = True
        return stats

    def session_context(self, payload: dict, stats: dict | None,
                        transcript_reader: Callable[..., dict],
                        transcript_finder: Callable[[str], str]) -> tuple[str, str]:
        session_id = (payload.get("session_id") or payload.get("sessionId")
                      or os.environ.get(self.session_env, "") or (stats or {}).get("session_id", ""))
        session_name = (stats or {}).get("session_name", "")
        if not session_name and session_id:
            path = payload.get("transcript_path") or transcript_finder(session_id)
            if path:
                session_name = transcript_reader(path).get("session_name", "")
        return session_id, session_name

    def debug_message(self, payload: dict, raw: str) -> str:
        return "hook event=%s raw=%s" % (payload.get("hook_event_name"), raw[:500])


HARNESS = ClaudeHarness()
