# -*- coding: utf-8 -*-
"""渠道注册表。新增渠道：在本目录写一个模块导出 CHANNEL，再登记到下面的元组里。"""

from __future__ import annotations

from . import lark
from .base import Channel, Message, STATUSES, SEND_STATUSES  # noqa: F401

DEFAULT_CHANNEL = "lark"

CHANNELS: dict[str, Channel] = {c.name: c for c in (
    lark.CHANNEL,
)}


def get_channel(name) -> Channel | None:
    """按名字取渠道；未登记或类型不对返回 None。缺省（None / 空串）视为飞书，兼容旧配置。"""
    if name is None or name == "":
        name = DEFAULT_CHANNEL
    if not isinstance(name, str):
        return None
    return CHANNELS.get(name.strip().lower())


def destination_fields() -> frozenset:
    """所有渠道的目的地字段并集 —— 这些都只能来自可信配置。"""
    keys = set()
    for ch in CHANNELS.values():
        keys.update(ch.dest_keys)
    return frozenset(keys)
