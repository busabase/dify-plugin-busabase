from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import change_result, node_ref, pick_slug, resolve_parent_folder, status_text


class CreateFolderTool(Tool):
    """nodes.createChangeRequest (create, nodeType folder) — POST /api/v1/nodes/change-requests"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        name = text_param(tool_parameters, "name")
        if not name:
            raise BusabaseError("`name` is required: the folder's name.")
        parent = resolve_parent_folder(client, text_param(tool_parameters, "parent"))
        slug = pick_slug(client, "folder", name, text_param(tool_parameters, "slug"))
        operation: dict[str, Any] = {
            "kind": "create",
            "nodeType": "folder",
            "slug": slug,
            "name": name,
            "description": text_param(tool_parameters, "description"),
        }
        if parent:
            operation["parentNodeId"] = parent["id"]
        message = text_param(tool_parameters, "message") or f"Create folder {name} via Dify"
        result = change_result(client, client.node_change_request([operation], message))
        where = f"folder {parent['name']!r}" if parent else "the workspace root"
        text = status_text(
            result,
            f"Created folder {name!r} (slug: {slug}, id: {result['nodeId']}) in {where}",
            f"a new folder {name!r} in {where}",
        )
        yield from emit(
            self,
            {**result, "slug": slug, "name": name, "parent": node_ref(parent) if parent else None, "message": message},
            text,
        )
