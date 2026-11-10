# -*- coding: utf-8 -*-
"""宿主工厂：模块导出 HARNESS 实例，再登记到下方注册表。"""

from __future__ import annotations

from . import claude, codex
from .base import Harness

DEFAULT_HARNESS = "claude"

# 顺序也是手动命令的环境识别优先级；保留 Claude 优先，兼容嵌套启动。
HARNESSES: dict[str, Harness] = {h.name: h for h in (claude.HARNESS, codex.HARNESS)}


def get_harness(name: str) -> Harness | None:
    """取已登记的宿主；未知名称或类型返回 None，不能悄悄切换宿主。"""
    return HARNESSES.get(name) if isinstance(name, str) else None
