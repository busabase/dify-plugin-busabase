"""Invoke a Dify Tool the way the plugin runtime does, and split its messages."""

from __future__ import annotations

from typing import Any

CREDENTIALS = {"base_url": "https://bb.example.com/", "api_key": "bb_test_key", "space_id": "spc_1"}


def run_tool(tool_cls: type, params: dict[str, Any], credentials: dict[str, Any] | None = None):
    """Invoke a Dify Tool the way the plugin runtime does and split its messages."""
    tool = tool_cls.from_credentials(credentials or CREDENTIALS)
    texts: list[str] = []
    jsons: list[dict[str, Any]] = []
    for message in tool.invoke(dict(params)):
        payload = message.message
        if hasattr(payload, "text"):
            texts.append(payload.text)
        elif hasattr(payload, "json_object"):
            jsons.append(payload.json_object)
    return "\n".join(texts), (jsons[0] if jsons else None)
