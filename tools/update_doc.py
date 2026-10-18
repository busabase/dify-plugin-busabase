from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import change_result, choice_param, line_count, node_of, node_ref, resolve_node, status_text


class UpdateDocTool(Tool):
    """nodes.updateContent — PUT /api/v1/nodes/{nodeId}/content with {kind: "doc", body}

    `append` reads the current body (nodes.get) and writes body + text. The
    endpoint takes an id only (a slug 404s), so the doc is resolved first.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        mode = choice_param(text_param(tool_parameters, "mode"), "mode", ("append", "replace"), "append")
        text_in = tool_parameters.get("text")
        if text_in is None or (mode == "append" and not str(text_in)):
            raise BusabaseError("`text` is required: the markdown to append, or the full new body for replace.")
        detail = resolve_node(client, text_param(tool_parameters, "doc"), ("doc",), "doc")
        node = node_of(detail)
        current = str(detail.get("body") or "")
        if mode == "append":
            separator = "" if not current or current.endswith("\n") else "\n"
            body = current + separator + str(text_in)
        else:
            body = str(text_in)
        base = {"doc": node_ref(node), "mode": mode, "totalLines": line_count(body), "totalChars": len(body)}
        if body == current:
            yield from emit(
                self,
                {"status": "unchanged", "merged": False, "changeRequestId": None, "nodeId": node.get("id"), **base},
                f"No change: doc {node.get('name')!r} already has exactly this content.",
            )
            return
        verb = "Append to" if mode == "append" else "Rewrite"
        message = text_param(tool_parameters, "message") or f"{verb} {node.get('name')} via Dify"
        result = change_result(client, client.update_node_content(str(node["id"]), {"kind": "doc", "body": body}, message))
        result["nodeId"] = result.get("nodeId") or node.get("id")
        did = "Appended to" if mode == "append" else "Replaced the body of"
        text = status_text(
            result,
            f"{did} doc {node.get('name')!r} ({node.get('id')}), now {line_count(body)} line(s)",
            f"an update to doc {node.get('name')!r} ({node.get('id')})",
        )
        yield from emit(self, {**result, **base, "message": message}, text)
